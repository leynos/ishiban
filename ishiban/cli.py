"""Local collector and server entrypoints.

For example, ``ishiban collect --workspace leynos`` starts observation, and
``ishiban serve`` serves the same database and Bun-built interface on loopback.
"""

import pathlib

import cyclopts
import msgspec
import uvicorn

from ishiban.api import create_app
from ishiban.collector import Collector, collector_lock
from ishiban.interface_state import load_signing_key
from ishiban.lody import read_catalogue
from ishiban.storage import Store

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


@app.command
async def collect(
    *,
    workspace: str = "leynos",
    state_directory: pathlib.Path = pathlib.Path(".ishiban"),
    github: bool = True,
) -> None:
    """Continuously observe one workspace without changing its Lody sessions.

    For example, ``ishiban collect --no-github`` leaves untitled PRs unclassified.
    """
    with collector_lock(state_directory):
        catalogue = await read_catalogue(workspace)
        config = WorkspaceConfig(
            workspace_id=catalogue.workspace_id, selector=workspace
        )
        store = Store(database_url(state_directory), catalogue.workspace_id)
        await store.initialize()
        marker = state_directory / "workspace.json"
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
    *, state_directory: pathlib.Path = pathlib.Path(".ishiban"), port: int = 8765
) -> None:
    """Serve the local board after starting a collector in another terminal.

    For example, ``ishiban serve --port 8765`` binds only to 127.0.0.1.

    Raises
    ------
    cyclopts.ValidationError
        If the collector identity or built UI is missing.
    """
    marker = state_directory / "workspace.json"
    if not marker.is_file():
        message = "Start 'ishiban collect --workspace leynos' before serving the board."
        raise cyclopts.ValidationError(message)
    config = msgspec.json.decode(marker.read_bytes(), type=WorkspaceConfig)
    assets = pathlib.Path("dist").resolve()
    if not (assets / "index.html").is_file():
        message = "Build the browser interface first with 'bun run build'."
        raise cyclopts.ValidationError(message)
    store = Store(database_url(state_directory), config.workspace_id)
    uvicorn.run(
        create_app(
            store,
            assets,
            workspace_slug=config.selector,
            cookie_secret=load_signing_key(state_directory),
        ),
        host="127.0.0.1",
        port=port,
        workers=1,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    app()
