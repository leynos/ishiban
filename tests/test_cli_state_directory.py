"""CLI commands resolve one shared XDG state directory from any working directory."""

import stat
import typing as typ
from unittest import mock

import pytest
from cli_state_support import (
    COLLECT_ARGV,
    default_state_directory,
    read_marker,
    run_cli,
    serve_assets,
    stub_catalogue,
    stub_collector,
)
from falcon import testing

from ishiban import cli

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox


def test_default_state_is_shared_across_working_directories(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """Collector and server launched elsewhere use the same XDG state."""
    stub_catalogue(cmd_mox)
    observer = stub_collector(monkeypatch)
    first = tmp_path / "first"
    second = tmp_path / "second"
    server = tmp_path / "server"
    for directory in (first, second, server):
        directory.mkdir()
    serve_assets(server)

    monkeypatch.chdir(first)
    run_cli(COLLECT_ARGV)
    monkeypatch.chdir(second)
    run_cli(COLLECT_ARGV)

    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)
    monkeypatch.chdir(server)
    run_cli(["serve"])

    state = default_state_directory(tmp_path)
    assert read_marker(state) == {"workspaceId": "w1", "selector": "leynos"}, (
        "The shared default must retain the collector's workspace identity."
    )
    assert (state / "observatory.sqlite3").is_file(), (
        "The journal must live in the shared default."
    )
    assert (state / "collector.lock").is_file(), (
        "The collector lock must stay beside the journal."
    )
    for directory in (first, second, server):
        assert not (directory / ".ishiban").exists(), (
            "No command may create working-directory state implicitly."
        )
    assert observer.await_count == 2, (
        "The collector must complete once from each working directory."
    )
    listener.assert_called_once()


def test_relative_override_stays_relative_to_the_caller(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """An explicit relative override keeps its existing working-directory meaning."""
    stub_catalogue(cmd_mox)
    stub_collector(monkeypatch)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)

    run_cli([*COLLECT_ARGV, "--state-directory", "local-state"])

    assert (working / "local-state" / "workspace.json").is_file(), (
        "A relative override must resolve against the caller's directory."
    )
    assert not default_state_directory(tmp_path).exists(), (
        "An explicit override must not also populate the default."
    )


def test_absolute_override_is_authoritative(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """An explicit absolute override replaces the shared default entirely."""
    stub_catalogue(cmd_mox)
    stub_collector(monkeypatch)
    state = tmp_path / "explicit-state"
    monkeypatch.chdir(tmp_path)

    run_cli([*COLLECT_ARGV, "--state-directory", str(state)])

    assert (state / "workspace.json").is_file(), (
        "The override must hold the workspace marker."
    )
    assert (state / "observatory.sqlite3").is_file(), (
        "The override must hold the journal."
    )
    assert not default_state_directory(tmp_path).exists(), (
        "The default must remain untouched when an override is supplied."
    )


@pytest.mark.asyncio
async def test_direct_collect_call_uses_the_shared_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """A direct command call resolves the same default as the parsed CLI."""
    stub_catalogue(cmd_mox)
    observer = stub_collector(monkeypatch)
    monkeypatch.chdir(tmp_path)

    await cli.collect(github=False)

    assert (default_state_directory(tmp_path) / "workspace.json").is_file(), (
        "A direct call must publish the marker in the shared default."
    )
    observer.assert_awaited_once()


def test_root_help_lists_both_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """The application help keeps exposing the two supported commands."""
    run_cli(["--help"])

    output = capsys.readouterr().out
    assert "collect" in output, "The collector must remain discoverable."
    assert "serve" in output, "The server must remain discoverable."


@pytest.mark.parametrize("command", ["collect", "serve"])
def test_command_help_documents_the_stated_default(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Help states the XDG default instead of rendering the omission marker."""
    run_cli([command, "--help"])

    output = capsys.readouterr().out
    assert "XDG_STATE_HOME/ishiban" in output, (
        "The stated default must name the XDG state directory."
    )
    assert "~/.local/state/ishiban" in output, (
        "The stated default must name the home fallback."
    )
    assert "None" not in output, "The omitted default must not render as None."


@pytest.mark.asyncio
async def test_serve_keeps_the_sidecar_and_signing_key_in_the_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """Derived state and the preference key follow the resolved directory."""
    stub_catalogue(cmd_mox)
    stub_collector(monkeypatch)
    server = tmp_path / "server"
    server.mkdir()
    serve_assets(server)
    monkeypatch.chdir(server)
    await cli.collect(github=False)
    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)

    run_cli(["serve"])

    state = default_state_directory(tmp_path)
    listener_options = listener.call_args.kwargs
    assert listener_options["host"] == "127.0.0.1", "The server must stay on loopback."
    assert listener_options["port"] == 8765, "The server uses its default port."
    assert listener_options["workers"] == 1, (
        "The local database supports one API worker."
    )
    application = listener.call_args.args[0]
    async with testing.ASGIConductor(application) as conductor:
        response = await conductor.simulate_get("/api/v1/snapshot")
    assert response.status_code == 200, "The shared default must serve reads."
    assert (state / "observatory.sqlite3.activity.sqlite3").is_file(), (
        "The activity sidecar must stay beside the journal."
    )
    key = state / "interface-state.key"
    first_key = key.read_bytes()
    assert stat.S_IMODE(key.stat().st_mode) == 0o600, (
        "The signing key must keep its private permissions."
    )

    run_cli(["serve"])

    assert key.read_bytes() == first_key, "Restarts must reuse the signing key."
    assert stat.S_IMODE(key.stat().st_mode) == 0o600, (
        "Reusing the key must not widen its permissions."
    )
