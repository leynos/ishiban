"""Run published collector and server examples through their CLI boundary."""

import dataclasses as dc
import json
import pathlib
import shlex
import typing as typ
from unittest import mock

import pytest
from documentation_examples import load_user_guide_examples
from pytest_bdd import given, scenarios, then, when

from ishiban import cli
from ishiban.collector import Collector

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

scenarios("features/user-guide-commands.feature")


@dc.dataclass(slots=True)
class GuideRun:
    """One isolated CLI run and its intercepted listener evidence."""

    state_directory: pathlib.Path
    observer: mock.AsyncMock
    listener: mock.Mock


@pytest.fixture
def published_examples() -> dict[str, str]:
    """Load the shipped guide once for this behavioural scenario.

    Returns
    -------
    dict[str, str]
        Marked command source from the published document.
    """
    return load_user_guide_examples()


@given("the published collector and server examples", target_fixture="commands")
def published_commands(
    published_examples: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Read both command lines from the shipped users' guide.

    Returns
    -------
    tuple[list[str], list[str]]
        Collector and server argv from their tested-example markers.
    """
    return shlex.split(published_examples["collect"]), shlex.split(
        published_examples["serve"]
    )


@when(
    "I run their Cyclopts commands with read-only Lody fixtures",
    target_fixture="guide_run",
)
def run_documented_cli(
    commands: tuple[list[str], list[str]],
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: object,
) -> GuideRun:
    """Parse published flags while replacing only external and endless edges.

    Returns
    -------
    GuideRun
        The resulting isolated state and intercepted listener.
    """
    collect_argv, serve_argv = commands
    assert collect_argv[:3] == serve_argv[:3] == ["uv", "run", "ishiban"], (
        "Both published commands must target the installed Ishiban CLI."
    )
    command_mocks = typ.cast("CmdMox", cmd_mox)
    command_mocks.mock("lody").with_args(
        "session", "list", "--workspace", "leynos", "--all", "--json"
    ).returns(stdout='{"ok":true,"workspaceId":"w1","sessions":[]}')
    observer = mock.AsyncMock()
    monkeypatch.setattr(Collector, "run", observer)
    monkeypatch.chdir(tmp_path)
    cli.app(
        collect_argv[3:],
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )

    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("<title>Ishiban</title>", encoding="utf-8")
    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)
    cli.app(
        serve_argv[3:],
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )
    return GuideRun(pathlib.Path.cwd() / ".ishiban", observer, listener)


@then("the collector identity reaches a loopback-only server")
def verify_documented_cli(guide_run: GuideRun) -> None:
    """Verify workspace identity persists without binding a real port."""
    config = json.loads((guide_run.state_directory / "workspace.json").read_text())
    assert config == {"workspaceId": "w1", "selector": "leynos"}, (
        "The collector must persist the selected workspace for the server."
    )
    guide_run.observer.assert_awaited_once()
    guide_run.listener.assert_called_once()
    kwargs = guide_run.listener.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1", "The server must stay on loopback."
    assert kwargs["port"] == 8765, "The documented server uses its default port."
    assert kwargs["workers"] == 1, "The local database supports one API worker."
