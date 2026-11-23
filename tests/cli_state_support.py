"""Shared command fixtures for the CLI state-directory contract tests.

These helpers belong only to ``test_cli_state_directory`` and
``test_cli_workspace_marker``. They replace the read-only catalogue command and
the endless collector loop; they are not application utilities.
"""

import typing as typ
from unittest import mock

import msgspec

from ishiban import cli
from ishiban.collector import Collector

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from cmd_mox import CmdMox

COLLECT_ARGV = ["collect", "--no-github"]


def catalogue_payload(*, workspace_id: str = "w1") -> str:
    """Return one valid read-only catalogue response body.

    Returns
    -------
    str
        JSON text understood by the Lody catalogue reader.
    """
    return msgspec.json.encode({
        "ok": True,
        "workspaceId": workspace_id,
        "sessions": [],
    }).decode()


def stub_catalogue(
    cmd_mox: CmdMox, *, workspace: str = "leynos", workspace_id: str = "w1"
) -> None:
    """Answer every catalogue refresh for one workspace selector."""
    cmd_mox.stub("lody").with_args(
        "session", "list", "--workspace", workspace, "--all", "--json"
    ).returns(stdout=catalogue_payload(workspace_id=workspace_id))


def stub_collector(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    """Replace the endless collector loop with a recorded completion.

    Returns
    -------
    unittest.mock.AsyncMock
        The replacement that records each collector invocation.
    """
    observer = mock.AsyncMock()
    monkeypatch.setattr(Collector, "run", observer)
    return observer


def run_cli(argv: list[str]) -> None:
    """Run one Cyclopts command without exiting the test process."""
    cli.app(
        argv,
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )


def serve_assets(directory: pathlib.Path) -> None:
    """Create the locally built interface that ``serve`` requires."""
    assets = directory / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("<title>Ishiban</title>", encoding="utf-8")


def read_marker(state_directory: pathlib.Path) -> dict[str, object]:
    """Decode one state directory's published workspace identity.

    Returns
    -------
    dict[str, object]
        The marker's camel-case public fields.
    """
    marker = state_directory / "workspace.json"
    return msgspec.json.decode(marker.read_bytes())


def default_state_directory(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return the default state directory selected by the autouse XDG fixture.

    Returns
    -------
    pathlib.Path
        The resolved default under this test's temporary XDG root.
    """
    return tmp_path / "xdg-state" / "ishiban"
