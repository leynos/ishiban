"""Run published collector, server and migration examples through their boundary."""

import dataclasses as dc
import json
import os
import pathlib  # ruff: ignore[typing-only-standard-library-import] - pytest-bdd resolves step annotations at runtime.
import shlex
import shutil
import stat
import subprocess  # ruff: ignore[suspicious-subprocess-import] - published repository examples, not external input.
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

LEGACY_FILES: dict[str, tuple[bytes, int]] = {
    "workspace.json": (b'{"workspaceId":"w1","selector":"leynos"}', 0o644),
    "observatory.sqlite3": (b"journal bytes", 0o644),
    "observatory.sqlite3-wal": (b"wal bytes", 0o600),
    "observatory.sqlite3.activity.sqlite3": (b"activity bytes", 0o644),
    "interface-state.key": (b"k" * 32, 0o600),
}


@dc.dataclass(slots=True)
class GuideRun:
    """One isolated CLI run and its intercepted listener evidence."""

    state_directory: pathlib.Path
    working_directories: tuple[pathlib.Path, pathlib.Path]
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
    isolated_xdg_state_home: pathlib.Path,
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
    command_mocks.stub("lody").with_args(
        "session", "list", "--workspace", "leynos", "--all", "--json"
    ).returns(stdout='{"ok":true,"workspaceId":"w1","sessions":[]}')
    observer = mock.AsyncMock()
    monkeypatch.setattr(Collector, "run", observer)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    collector_directory = tmp_path / "collector-checkout"
    collector_directory.mkdir()
    monkeypatch.chdir(collector_directory)
    cli.app(
        collect_argv[3:],
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )

    server_directory = tmp_path / "server-checkout"
    assets = server_directory / "dist"
    assets.mkdir(parents=True)
    (assets / "index.html").write_text("<title>Ishiban</title>", encoding="utf-8")
    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)
    monkeypatch.chdir(server_directory)
    cli.app(
        serve_argv[3:],
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )
    return GuideRun(
        isolated_xdg_state_home / "ishiban",
        (collector_directory, server_directory),
        observer,
        listener,
    )


@then("the collector identity reaches a loopback-only server")
def verify_documented_cli(guide_run: GuideRun) -> None:
    """Verify the shared identity persists without binding a real port."""
    config = json.loads((guide_run.state_directory / "workspace.json").read_text())
    assert config == {"workspaceId": "w1", "selector": "leynos"}, (
        "The collector must persist the selected workspace for the server."
    )
    for directory in guide_run.working_directories:
        assert not (directory / ".ishiban").exists(), (
            "The published commands must not create working-directory state."
        )
    guide_run.observer.assert_awaited_once()
    guide_run.listener.assert_called_once()
    kwargs = guide_run.listener.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1", "The server must stay on loopback."
    assert kwargs["port"] == 8765, "The documented server uses its default port."
    assert kwargs["workers"] == 1, "The local database supports one API worker."


def _run_bash_example(
    source: str, working_directory: pathlib.Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one published Bash example in an isolated directory.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed example with captured diagnostic text.
    """
    bash = shutil.which("bash")
    assert bash is not None, "The published example requires an installed bash."
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - the repository's own published example.
        [bash, "-c", source],
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )


def _seed_legacy_state(directory: pathlib.Path) -> None:
    """Create representative legacy files with private and shared modes."""
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    for name, (content, mode) in LEGACY_FILES.items():
        path = directory / name
        path.write_bytes(content)
        path.chmod(mode)


def _isolated_environment(tmp_path: pathlib.Path) -> dict[str, str]:
    """Return a subprocess environment with private home and XDG roots.

    Returns
    -------
    dict[str, str]
        The inherited environment with isolated HOME and XDG_STATE_HOME.
    """
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path / "home")
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    return environment


def test_documented_migration_moves_legacy_state_unchanged(
    tmp_path: pathlib.Path, published_examples: dict[str, str]
) -> None:
    """The published move relocates every legacy file with its exact bytes."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _seed_legacy_state(checkout / ".ishiban")

    result = _run_bash_example(
        published_examples["migrate-state"], checkout, _isolated_environment(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    destination = tmp_path / "xdg-state" / "ishiban"
    assert not (checkout / ".ishiban").exists(), "The move must remove the old path."
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700, (
        "The moved directory must retain its private mode."
    )
    for name, (content, mode) in LEGACY_FILES.items():
        moved = destination / name
        assert moved.read_bytes() == content, f"{name} must keep its exact bytes."
        assert stat.S_IMODE(moved.stat().st_mode) == mode, (
            f"{name} must keep its permissions."
        )


def test_documented_migration_refuses_an_existing_destination(
    tmp_path: pathlib.Path, published_examples: dict[str, str]
) -> None:
    """An occupied destination stops the example before either tree changes."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _seed_legacy_state(checkout / ".ishiban")
    destination = tmp_path / "xdg-state" / "ishiban"
    destination.mkdir(parents=True)
    sentinel = destination / "workspace.json"
    sentinel.write_bytes(b"existing state")

    result = _run_bash_example(
        published_examples["migrate-state"], checkout, _isolated_environment(tmp_path)
    )

    assert result.returncode != 0, "An occupied destination must fail the example."
    assert "Refusing to merge" in result.stderr, "The refusal must be explicit."
    assert (checkout / ".ishiban" / "workspace.json").is_file(), (
        "The legacy directory must remain in place."
    )
    assert sentinel.read_bytes() == b"existing state", (
        "The existing destination must be unchanged."
    )
    assert not (destination / "observatory.sqlite3").exists(), (
        "No legacy file may be merged into the destination."
    )
