"""Local collector and server entrypoints.

For example, ``ishiban collect --workspace leynos`` starts observation, and
``ishiban serve`` serves the same database and Bun-built interface on loopback.
"""

import os
import pathlib
import sys
import typing as typ

import cyclopts
import msgspec
import uvicorn
from cyclopts import Parameter

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from ishiban.api import create_app
from ishiban.collector import Collector, collector_lock
from ishiban.interface_state import load_signing_key
from ishiban.lody import read_catalogue
from ishiban.storage import Store

APPLICATION_DIRECTORY = "ishiban"
MARKER_FILENAME = "workspace.json"
LEGACY_STATE_DIRECTORY = pathlib.Path(".ishiban")
XDG_STATE_HOME = "XDG_STATE_HOME"
UNRESOLVABLE_STATE_DIRECTORY = (
    "Cannot resolve the default state directory. Set an absolute "
    "XDG_STATE_HOME, set a non-empty absolute HOME, or pass "
    "a separate --state-directory."
)

# The omission marker lets Cyclopts distinguish an explicit override from the
# resolved default; the display shows the stated default instead of ``None``.
STATE_DIRECTORY_PARAMETER = Parameter(
    show_default=False,
    help=(
        "Private state directory. Default: $XDG_STATE_HOME/ishiban, or "
        "~/.local/state/ishiban when XDG_STATE_HOME is unset or invalid."
    ),
)

app = cyclopts.App(help="Read-only Lody engineering observatory.")


class WorkspaceConfig(msgspec.Struct, rename="camel"):
    """Persist a public workspace identity without any CLI credentials."""

    workspace_id: str
    selector: str


def database_url(directory: pathlib.Path) -> str:
    """Return an absolute SQLite URL; for example, use the shared state directory.

    Returns
    -------
    str
        Absolute SQLite URL for the chosen state directory.
    """
    return f"sqlite+aiosqlite:///{directory.resolve() / 'observatory.sqlite3'}"


def default_state_directory(*, command_chain: cabc.Sequence[str]) -> pathlib.Path:
    """Return the per-user default state directory without touching the filesystem.

    The shared default belongs only to the CLI's ``collect`` and ``serve``
    commands. Standalone Alembic commands keep their separate
    repository-relative target. A non-empty absolute ``XDG_STATE_HOME`` wins;
    unset, empty and relative values are invalid under the XDG Base Directory
    Specification and fall back to ``~/.local/state/ishiban``. Neither ``~`` nor
    environment variables are expanded inside a configured value, and the
    result is neither created nor resolved.

    Parameters
    ----------
    command_chain : collections.abc.Sequence[str]
        The invoking command, used only to render a Cyclopts diagnostic.

    Returns
    -------
    pathlib.Path
        An absolute state directory independent of the working directory.

    Notes
    -----
    An unusable environment raises ``cyclopts.ValidationError`` through
    :func:`_home_directory`.

    Examples
    --------
    With ``XDG_STATE_HOME=/srv/state`` the result is ``/srv/state/ishiban``.
    """
    configured = os.environ.get(XDG_STATE_HOME)
    if configured:
        state_root = pathlib.Path(configured)
        if state_root.is_absolute():
            return state_root / APPLICATION_DIRECTORY
    home = _home_directory(command_chain=command_chain)
    return home / ".local" / "state" / APPLICATION_DIRECTORY


def _home_directory(*, command_chain: cabc.Sequence[str]) -> pathlib.Path:
    """Return an absolute home directory or reject an unusable environment.

    Returns
    -------
    pathlib.Path
        The configured home directory.

    Raises
    ------
    cyclopts.ValidationError
        If HOME is empty or relative, or no home directory can be determined.
    """
    configured = os.environ.get("HOME")
    if configured is None:
        try:
            home = pathlib.Path.home()
        except RuntimeError as error:
            raise cyclopts.ValidationError(
                exception_message=UNRESOLVABLE_STATE_DIRECTORY,
                command_chain=command_chain,
            ) from error
    else:
        home = pathlib.Path(configured)
    if not home.is_absolute():
        raise cyclopts.ValidationError(
            exception_message=UNRESOLVABLE_STATE_DIRECTORY,
            command_chain=command_chain,
        )
    return home


def _selected_state_directory(
    state_directory: pathlib.Path | None, *, command_chain: cabc.Sequence[str]
) -> pathlib.Path:
    """Return the explicit directory or the shared XDG default state directory.

    Parameters
    ----------
    state_directory : pathlib.Path or None
        The explicit ``--state-directory`` value, or None when it was omitted.
    command_chain : collections.abc.Sequence[str]
        The invoking command, used only to render a Cyclopts diagnostic.

    Returns
    -------
    pathlib.Path
        The caller's path unchanged, or the resolved default.
    """
    if state_directory is not None:
        return state_directory
    resolved = default_state_directory(command_chain=command_chain)
    _warn_about_legacy_state(resolved)
    return resolved


def _warn_about_legacy_state(resolved: pathlib.Path) -> None:
    """Mention untouched working-directory state without reading or moving it.

    Parameters
    ----------
    resolved : pathlib.Path
        The default state directory selected for this invocation.
    """
    legacy = pathlib.Path.cwd() / LEGACY_STATE_DIRECTORY
    try:
        if not (legacy / MARKER_FILENAME).is_file():
            return
        is_same_directory = legacy.resolve() == resolved.resolve()
    except OSError:
        return
    if is_same_directory:
        return
    print(
        f"Legacy state found in {legacy}; the default is now {resolved}. "
        f"Move that directory, or pass '--state-directory {legacy}' to keep "
        "using it. See the users' guide for migration steps.",
        file=sys.stderr,
    )


def _read_workspace_config(directory: pathlib.Path) -> WorkspaceConfig | None:
    """Read the saved workspace identity without creating or replacing it.

    Parameters
    ----------
    directory : pathlib.Path
        The state directory that may contain a workspace marker.

    Returns
    -------
    WorkspaceConfig or None
        The saved identity, or None when no marker file exists.

    Notes
    -----
    A marker that is not a valid workspace identity propagates the decoder's
    ``msgspec.DecodeError`` so callers decide whether to reject or report it.
    """
    marker = directory / MARKER_FILENAME
    if not marker.is_file():
        return None
    return msgspec.json.decode(marker.read_bytes(), type=WorkspaceConfig)


def _require_workspace_identity(
    directory: pathlib.Path, workspace: str, workspace_id: str
) -> None:
    """Refuse to replace an unreadable or foreign workspace identity.

    Parameters
    ----------
    directory : pathlib.Path
        The state directory selected for this collector run.
    workspace : str
        The workspace selector requested on the command line.
    workspace_id : str
        The opaque workspace identity reported by the catalogue.

    Raises
    ------
    cyclopts.ValidationError
        If the marker is undecodable or names a different workspace.
    """
    try:
        saved = _read_workspace_config(directory)
    except msgspec.DecodeError as error:
        message = (
            f"Cannot read the saved workspace identity in {directory}. The "
            "existing state is left untouched; pass a separate "
            "--state-directory for this workspace."
        )
        raise cyclopts.ValidationError(
            exception_message=message, command_chain=("collect",)
        ) from error
    if saved is None or saved.workspace_id == workspace_id:
        return
    message = (
        f"The state directory {directory} belongs to workspace "
        f"{saved.selector!r} ({saved.workspace_id}); it will not be replaced "
        f"by {workspace!r} ({workspace_id}). Pass a separate "
        "--state-directory for each workspace."
    )
    raise cyclopts.ValidationError(
        exception_message=message, command_chain=("collect",)
    )


@app.command
async def collect(
    *,
    workspace: str = "leynos",
    state_directory: typ.Annotated[
        pathlib.Path | None, STATE_DIRECTORY_PARAMETER
    ] = None,
    github: bool = True,
) -> None:
    """Continuously observe one workspace without changing its Lody sessions.

    For example, ``ishiban collect --no-github`` leaves untitled PRs unclassified.
    """
    directory = _selected_state_directory(state_directory, command_chain=("collect",))
    with collector_lock(directory):
        catalogue = await read_catalogue(workspace)
        _require_workspace_identity(directory, workspace, catalogue.workspace_id)
        config = WorkspaceConfig(
            workspace_id=catalogue.workspace_id, selector=workspace
        )
        store = Store(database_url(directory), catalogue.workspace_id)
        await store.initialize()
        marker = directory / MARKER_FILENAME
        temporary = marker.with_suffix(".tmp")
        temporary.write_bytes(msgspec.json.encode(config))
        temporary.replace(marker)
        print(
            "Workspace catalogue connected. Start 'ishiban serve' in another terminal."
        )
        try:
            await Collector(store, workspace, github=github).run(catalogue)
        finally:
            await store.close()


@app.command
def serve(
    *,
    state_directory: typ.Annotated[
        pathlib.Path | None, STATE_DIRECTORY_PARAMETER
    ] = None,
    port: int = 8765,
) -> None:
    """Serve the local board after starting a collector in another terminal.

    For example, ``ishiban serve --port 8765`` binds only to 127.0.0.1.

    Raises
    ------
    cyclopts.ValidationError
        If the collector identity or built UI is missing.
    """
    directory = _selected_state_directory(state_directory, command_chain=("serve",))
    try:
        config = _read_workspace_config(directory)
    except msgspec.DecodeError as error:
        message = (
            f"Cannot read the saved workspace identity in {directory.resolve()}. "
            "Start 'ishiban collect --workspace leynos' again, or pass the "
            "--state-directory that holds this workspace."
        )
        raise cyclopts.ValidationError(
            exception_message=message, command_chain=("serve",)
        ) from error
    if config is None:
        message = (
            f"No saved workspace identity in {directory.resolve()}. Start "
            "'ishiban collect --workspace leynos' before serving the board."
        )
        raise cyclopts.ValidationError(
            exception_message=message, command_chain=("serve",)
        )
    assets = pathlib.Path("dist").resolve()
    if not (assets / "index.html").is_file():
        message = "Build the browser interface first with 'bun run build'."
        raise cyclopts.ValidationError(
            exception_message=message, command_chain=("serve",)
        )
    store = Store(database_url(directory), config.workspace_id)
    uvicorn.run(
        create_app(
            store,
            assets,
            workspace_slug=config.selector,
            cookie_secret=load_signing_key(directory),
        ),
        host="127.0.0.1",
        port=port,
        workers=1,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    app()
