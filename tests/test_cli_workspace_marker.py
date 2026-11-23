"""The collector protects the saved workspace identity and reports legacy state."""

import typing as typ

import cyclopts
import msgspec
import pytest
from cli_state_support import (
    COLLECT_ARGV,
    default_state_directory,
    read_marker,
    run_cli,
    stub_catalogue,
    stub_collector,
)

if typ.TYPE_CHECKING:
    import pathlib
    from unittest import mock

    from cmd_mox import CmdMox


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


def _assert_rejection_preserved(
    state: pathlib.Path, sentinel: bytes, observer: mock.AsyncMock
) -> None:
    """Check that a refused collector changed neither the marker nor the journal."""
    assert (state / "workspace.json").read_bytes() == sentinel, (
        "Rejected state must retain its exact marker bytes."
    )
    assert not (state / "observatory.sqlite3").exists(), (
        "Rejected state must not initialize a journal."
    )
    observer.assert_not_awaited()


@pytest.mark.parametrize("use_default", [True, False], ids=["default", "explicit"])
def test_collect_refuses_a_foreign_workspace_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    *,
    use_default: bool,
) -> None:
    """A marker for another workspace is never replaced or journalled over."""
    stub_catalogue(cmd_mox, workspace_id="w1")
    observer = stub_collector(monkeypatch)
    state = default_state_directory(tmp_path) if use_default else tmp_path / "state"
    sentinel = _write_marker(
        state, msgspec.json.encode({"workspaceId": "w2", "selector": "other"})
    )
    monkeypatch.chdir(tmp_path)
    argv = list(COLLECT_ARGV)
    if not use_default:
        argv.extend(["--state-directory", str(state)])

    with pytest.raises(cyclopts.ValidationError) as rejected:
        run_cli(argv)

    message = str(rejected.value)
    assert message.endswith(
        "belongs to workspace 'other' (w2); it will not be replaced by "
        "'leynos' (w1). Pass a separate --state-directory for each workspace."
    ), "The diagnostic must name both selectors and the separate-directory remedy."
    _assert_rejection_preserved(state, sentinel, observer)


def test_collect_refuses_an_undecodable_workspace_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """A corrupt marker is reported rather than silently overwritten."""
    stub_catalogue(cmd_mox)
    observer = stub_collector(monkeypatch)
    state = tmp_path / "state"
    sentinel = _write_marker(state, b"not a workspace identity")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        cyclopts.ValidationError, match="Cannot read the saved workspace identity"
    ):
        run_cli([*COLLECT_ARGV, "--state-directory", str(state)])

    _assert_rejection_preserved(state, sentinel, observer)


def test_collect_republishes_the_requested_selector_for_the_same_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """A matching workspace keeps its journal but accepts the new selector."""
    stub_catalogue(cmd_mox, workspace="second", workspace_id="w1")
    stub_collector(monkeypatch)
    state = tmp_path / "state"
    _write_marker(state, msgspec.json.encode({"workspaceId": "w1", "selector": "old"}))
    monkeypatch.chdir(tmp_path)

    run_cli([
        "collect",
        "--workspace",
        "second",
        "--no-github",
        "--state-directory",
        str(state),
    ])

    assert read_marker(state) == {"workspaceId": "w1", "selector": "second"}, (
        "The requested selector must replace the saved one for the same workspace."
    )
    assert (state / "observatory.sqlite3").is_file(), (
        "A matching identity must retain and initialize its journal."
    )


def test_default_collect_reports_legacy_state_without_changing_it(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Legacy working-directory state produces one read-only stderr notice."""
    stub_catalogue(cmd_mox)
    stub_collector(monkeypatch)
    legacy = tmp_path / ".ishiban"
    marker_bytes = _write_marker(
        legacy, msgspec.json.encode({"workspaceId": "w0", "selector": "legacy"})
    )
    (legacy / "observatory.sqlite3").write_bytes(b"legacy journal")
    monkeypatch.chdir(tmp_path)

    run_cli(COLLECT_ARGV)

    message = capsys.readouterr().err
    assert "Legacy state found" in message, "The notice must be explicit."
    assert str(legacy) in message, "The legacy path must be named."
    assert str(default_state_directory(tmp_path)) in message, (
        "The resolved default must be named."
    )
    assert "--state-directory" in message, "The override remedy must be offered."
    assert (legacy / "workspace.json").read_bytes() == marker_bytes, (
        "The legacy marker must be untouched."
    )
    assert (legacy / "observatory.sqlite3").read_bytes() == b"legacy journal", (
        "The legacy journal must be untouched."
    )
    assert (default_state_directory(tmp_path) / "workspace.json").is_file(), (
        "The collector must still use the resolved default."
    )


def test_explicit_override_does_not_report_legacy_state(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A caller who chose a directory is not warned about another one."""
    stub_catalogue(cmd_mox)
    stub_collector(monkeypatch)
    _write_marker(tmp_path / ".ishiban", b'{"workspaceId":"w0","selector":"legacy"}')
    monkeypatch.chdir(tmp_path)

    run_cli([*COLLECT_ARGV, "--state-directory", str(tmp_path / "explicit")])

    assert "Legacy state found" not in capsys.readouterr().err, (
        "An explicit override must not report working-directory state."
    )
