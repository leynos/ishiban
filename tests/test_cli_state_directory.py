"""CLI state resolution shares one XDG directory without abandoning old state."""

import stat
import typing as typ
from unittest import mock

import cyclopts
import msgspec
import pytest
from falcon import testing

from ishiban import cli
from ishiban.collector import Collector

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox

COLLECT_ARGV = ["collect", "--no-github"]


def _catalogue_payload(
    *, workspace_id: str = "w1", sessions: list[dict[str, object]] | None = None
) -> str:
    """Return one valid read-only catalogue response for the command fixture.

    Returns
    -------
    str
        JSON text understood by the Lody catalogue reader.
    """
    return msgspec.json.encode({
        "ok": True,
        "workspaceId": workspace_id,
        "sessions": sessions or [],
    }).decode()


def _stub_catalogue(
    cmd_mox: CmdMox, *, workspace: str = "leynos", workspace_id: str = "w1"
) -> None:
    """Answer every catalogue refresh for one workspace selector."""
    cmd_mox.stub("lody").with_args(
        "session", "list", "--workspace", workspace, "--all", "--json"
    ).returns(stdout=_catalogue_payload(workspace_id=workspace_id))


def _run(argv: list[str]) -> None:
    """Run one Cyclopts command without exiting the test process."""
    cli.app(
        argv,
        exit_on_error=False,
        print_error=False,
        result_action="return_value",
    )


def _serve_assets(directory: pathlib.Path) -> None:
    """Create the locally built interface that ``serve`` requires."""
    assets = directory / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("<title>Ishiban</title>", encoding="utf-8")


@pytest.fixture
def completed_collector(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    """Replace the endless collector loop with a recorded completion.

    Returns
    -------
    unittest.mock.AsyncMock
        The replacement that records each collector invocation.
    """
    observer = mock.AsyncMock()
    monkeypatch.setattr(Collector, "run", observer)
    return observer


def test_default_state_is_shared_across_working_directories(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """Collector and server launched elsewhere use the same XDG state."""
    _stub_catalogue(cmd_mox)
    first = tmp_path / "first"
    second = tmp_path / "second"
    server = tmp_path / "server"
    for directory in (first, second, server):
        directory.mkdir()
    _serve_assets(server)

    monkeypatch.chdir(first)
    _run(COLLECT_ARGV)
    monkeypatch.chdir(second)
    _run(COLLECT_ARGV)

    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)
    monkeypatch.chdir(server)
    _run(["serve"])

    state = isolated_xdg_state_home / "ishiban"
    marker = msgspec.json.decode((state / "workspace.json").read_bytes())
    assert marker == {"workspaceId": "w1", "selector": "leynos"}, (
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
    assert completed_collector.await_count == 2, (
        "The collector must complete once from each working directory."
    )
    listener.assert_called_once()


def test_relative_override_stays_relative_to_the_caller(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """An explicit relative override keeps its existing working-directory meaning."""
    _stub_catalogue(cmd_mox)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)

    _run([*COLLECT_ARGV, "--state-directory", "local-state"])

    assert (working / "local-state" / "workspace.json").is_file(), (
        "A relative override must resolve against the caller's directory."
    )
    assert not (isolated_xdg_state_home / "ishiban").exists(), (
        "An explicit override must not also populate the default."
    )


def test_absolute_override_is_authoritative(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """An explicit absolute override replaces the shared default entirely."""
    _stub_catalogue(cmd_mox)
    state = tmp_path / "explicit-state"
    monkeypatch.chdir(tmp_path)

    _run([*COLLECT_ARGV, "--state-directory", str(state)])

    assert (state / "workspace.json").is_file()
    assert (state / "observatory.sqlite3").is_file()
    assert not (isolated_xdg_state_home / "ishiban").exists(), (
        "The default must remain untouched when an override is supplied."
    )


@pytest.mark.asyncio
async def test_direct_collect_call_uses_the_shared_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """A direct command call resolves the same default as the parsed CLI."""
    _stub_catalogue(cmd_mox)
    monkeypatch.chdir(tmp_path)

    await cli.collect(github=False)

    assert (isolated_xdg_state_home / "ishiban" / "workspace.json").is_file()
    completed_collector.assert_awaited_once()


def test_root_help_lists_both_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """The application help keeps exposing the two supported commands."""
    _run(["--help"])

    output = capsys.readouterr().out
    assert "collect" in output, "The collector must remain discoverable."
    assert "serve" in output, "The server must remain discoverable."


@pytest.mark.parametrize("command", ["collect", "serve"])
def test_command_help_documents_the_stated_default(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Help states the XDG default instead of rendering the omission marker."""
    _run([command, "--help"])

    output = capsys.readouterr().out
    assert "XDG_STATE_HOME/ishiban" in output, (
        "The stated default must name the XDG state directory."
    )
    assert "~/.local/state/ishiban" in output, (
        "The stated default must name the home fallback."
    )
    assert "None" not in output, "The omitted default must not render as None."


def _write_marker(directory: pathlib.Path, raw: bytes) -> bytes:
    """Write one workspace marker and return its exact bytes.

    Returns
    -------
    bytes
        The sentinel content written to the marker file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "workspace.json").write_bytes(raw)
    return raw


@pytest.mark.parametrize("use_default", [True, False], ids=["default", "explicit"])
def test_collect_refuses_a_foreign_workspace_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
    *,
    use_default: bool,
) -> None:
    """A marker for another workspace is never replaced or journalled over."""
    _stub_catalogue(cmd_mox, workspace_id="w1")
    state = isolated_xdg_state_home / "ishiban" if use_default else tmp_path / "state"
    sentinel = _write_marker(
        state, msgspec.json.encode({"workspaceId": "w2", "selector": "other"})
    )
    monkeypatch.chdir(tmp_path)
    argv = list(COLLECT_ARGV)
    if not use_default:
        argv.extend(["--state-directory", str(state)])

    with pytest.raises(cyclopts.ValidationError) as rejected:
        _run(argv)

    message = str(rejected.value)
    assert "other" in message, "The saved selector must be named."
    assert "leynos" in message, "The requested selector must be named."
    assert "--state-directory" in message, "The remedy must name the override."
    assert (state / "workspace.json").read_bytes() == sentinel, (
        "Rejected state must retain its exact marker bytes."
    )
    assert not (state / "observatory.sqlite3").exists(), (
        "Rejected state must not initialize a journal."
    )
    completed_collector.assert_not_awaited()


def test_collect_refuses_an_undecodable_workspace_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
) -> None:
    """A corrupt marker is reported rather than silently overwritten."""
    _stub_catalogue(cmd_mox)
    state = tmp_path / "state"
    sentinel = _write_marker(state, b"not a workspace identity")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        cyclopts.ValidationError, match="Cannot read the saved workspace identity"
    ):
        _run([*COLLECT_ARGV, "--state-directory", str(state)])

    assert (state / "workspace.json").read_bytes() == sentinel
    assert not (state / "observatory.sqlite3").exists()
    completed_collector.assert_not_awaited()


def test_collect_republishes_the_requested_selector_for_the_same_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
) -> None:
    """A matching workspace keeps its journal but accepts the new selector."""
    _stub_catalogue(cmd_mox, workspace="second", workspace_id="w1")
    state = tmp_path / "state"
    _write_marker(state, msgspec.json.encode({"workspaceId": "w1", "selector": "old"}))
    monkeypatch.chdir(tmp_path)

    _run([
        "collect",
        "--workspace",
        "second",
        "--no-github",
        "--state-directory",
        str(state),
    ])

    marker = msgspec.json.decode((state / "workspace.json").read_bytes())
    assert marker == {"workspaceId": "w1", "selector": "second"}, (
        "The requested selector must replace the saved one for the same workspace."
    )
    assert (state / "observatory.sqlite3").is_file(), (
        "A matching identity must retain and initialize its journal."
    )


def test_default_collect_reports_legacy_state_without_changing_it(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    capsys: pytest.CaptureFixture[str],
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """Legacy working-directory state produces one read-only stderr notice."""
    _stub_catalogue(cmd_mox)
    legacy = tmp_path / ".ishiban"
    marker_bytes = _write_marker(
        legacy, msgspec.json.encode({"workspaceId": "w0", "selector": "legacy"})
    )
    (legacy / "observatory.sqlite3").write_bytes(b"legacy journal")
    monkeypatch.chdir(tmp_path)

    _run(COLLECT_ARGV)

    message = capsys.readouterr().err
    assert "Legacy state found" in message, "The notice must be explicit."
    assert str(legacy) in message, "The legacy path must be named."
    assert str(isolated_xdg_state_home / "ishiban") in message, (
        "The resolved default must be named."
    )
    assert "--state-directory" in message, "The override remedy must be offered."
    assert (legacy / "workspace.json").read_bytes() == marker_bytes, (
        "The legacy marker must be untouched."
    )
    assert (legacy / "observatory.sqlite3").read_bytes() == b"legacy journal", (
        "The legacy journal must be untouched."
    )
    assert (isolated_xdg_state_home / "ishiban" / "workspace.json").is_file(), (
        "The collector must still use the resolved default."
    )


def test_explicit_override_does_not_report_legacy_state(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A caller who chose a directory is not warned about another one."""
    _stub_catalogue(cmd_mox)
    _write_marker(tmp_path / ".ishiban", b'{"workspaceId":"w0","selector":"legacy"}')
    monkeypatch.chdir(tmp_path)

    _run([*COLLECT_ARGV, "--state-directory", str(tmp_path / "explicit")])

    assert "Legacy state found" not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_serve_keeps_the_sidecar_and_signing_key_in_the_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    completed_collector: mock.AsyncMock,
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """Derived state and the preference key follow the resolved directory."""
    _stub_catalogue(cmd_mox)
    server = tmp_path / "server"
    server.mkdir()
    _serve_assets(server)
    monkeypatch.chdir(server)
    await cli.collect(github=False)
    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)

    _run(["serve"])

    state = isolated_xdg_state_home / "ishiban"
    assert listener.call_args.kwargs == {
        "host": "127.0.0.1",
        "port": 8765,
        "workers": 1,
        "timeout_graceful_shutdown": 3,
    }, "Listener options remain the existing deployment contract."
    application = typ.cast("object", listener.call_args.args[0])
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

    _run(["serve"])

    assert key.read_bytes() == first_key, "Restarts must reuse the signing key."
    assert stat.S_IMODE(key.stat().st_mode) == 0o600, (
        "Reusing the key must not widen its permissions."
    )
