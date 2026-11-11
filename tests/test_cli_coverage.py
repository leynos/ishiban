"""CLI bootstrap preserves workspace identity and closes bounded local resources."""

import errno
import typing as typ
from unittest import mock

import cyclopts
import msgspec
import pytest
from falcon import testing

from ishiban import cli
from ishiban.collector import Collector, collector_lock
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox
    from syrupy.assertion import SnapshotAssertion


@pytest.mark.asyncio
@pytest.mark.parametrize("source_error", [None, RuntimeError("source failed")])
async def test_collect_persists_identity_and_releases_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    source_error: RuntimeError | None,
) -> None:
    """Both normal completion and source failure leave reusable collector state."""
    cmd_mox.mock("lody").with_args(
        "session", "list", "--workspace", "leynos", "--all", "--json"
    ).returns(stdout='{"ok":true,"workspaceId":"w1","sessions":[]}')
    run = mock.AsyncMock(side_effect=source_error)
    monkeypatch.setattr(Collector, "run", run)
    state = tmp_path / "state"
    if source_error is None:
        await cli.collect(state_directory=state, github=False)
    else:
        with pytest.raises(RuntimeError, match="source failed"):
            await cli.collect(state_directory=state, github=False)
    marker = msgspec.json.decode((state / "workspace.json").read_bytes())
    assert marker == {"workspaceId": "w1", "selector": "leynos"}, (
        "Server bootstrap must retain the authenticated workspace identity."
    )
    assert not (state / "workspace.tmp").exists(), "The identity rename must be atomic."
    assert (state / "observatory.sqlite3").is_file(), "The journal must be initialized."
    run.assert_awaited_once()
    with collector_lock(state):
        assert marker["workspaceId"] == "w1", "Collector ownership must be released."


@pytest.mark.asyncio
async def test_collect_rejects_competing_owner_before_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
) -> None:
    """A held state-directory lock blocks CLI reads and journal creation."""
    cmd_mox.mock("lody").with_args(
        "session", "list", "--workspace", "leynos", "--all", "--json"
    ).returns(stdout='{"ok":true,"workspaceId":"w1","sessions":[]}')
    catalogue_reader = mock.AsyncMock(wraps=cli.read_catalogue)
    monkeypatch.setattr(cli, "read_catalogue", catalogue_reader)
    run = mock.AsyncMock()
    monkeypatch.setattr(Collector, "run", run)
    state = tmp_path / "state"

    with collector_lock(state):
        with pytest.raises(BlockingIOError) as rejected:
            await cli.collect(state_directory=state, github=False)
        assert rejected.value.errno == errno.EWOULDBLOCK, (
            "A competing CLI collector must fail on the held ownership lock."
        )
        catalogue_reader.assert_not_awaited()
        run.assert_not_awaited()
        assert not (state / "workspace.json").exists(), (
            "The rejected collector must not publish a workspace identity."
        )
        assert not (state / "observatory.sqlite3").exists(), (
            "The rejected collector must not initialize or write the journal."
        )

    await cli.collect(state_directory=state, github=False)
    catalogue_reader.assert_awaited_once_with("leynos")
    run.assert_awaited_once()
    assert (state / "observatory.sqlite3").is_file(), (
        "A later collector must acquire ownership and initialize the journal."
    )


def test_serve_requires_the_collector_identity(tmp_path: Path) -> None:
    """An uninitialized state directory must not start a listener."""
    with pytest.raises(cyclopts.ValidationError, match="Start 'ishiban collect"):
        cli.app(
            ["serve", "--state-directory", str(tmp_path)],
            exit_on_error=False,
            print_error=False,
        )


def test_serve_requires_the_built_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace marker alone cannot serve missing browser assets."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workspace.json").write_text(
        '{"workspaceId":"w1","selector":"leynos"}', encoding="utf-8"
    )
    with pytest.raises(cyclopts.ValidationError, match="Build the browser interface"):
        cli.app(
            ["serve", "--state-directory", str(tmp_path)],
            exit_on_error=False,
            print_error=False,
        )


@pytest.mark.asyncio
async def test_serve_binds_loopback_with_the_saved_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion
) -> None:
    """The CLI constructs the real ASGI app but delegates only one local listener."""
    monkeypatch.chdir(tmp_path)
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("<title>Ishiban</title>", encoding="utf-8")
    (tmp_path / "workspace.json").write_text(
        '{"workspaceId":"w1","selector":"leynos"}', encoding="utf-8"
    )
    store = Store(cli.database_url(tmp_path), "w1")
    await store.initialize()
    await store.close()
    listener = mock.Mock()
    monkeypatch.setattr(cli.uvicorn, "run", listener)
    cli.serve(state_directory=tmp_path, port=8877)
    listener.assert_called_once()
    invocation = listener.call_args
    assert invocation is not None, "The CLI must delegate to the ASGI listener."
    assert invocation.kwargs == snapshot, (
        "Listener options form a stable deployment contract."
    )
    assert invocation.kwargs["host"] == "127.0.0.1", (
        "The listener must remain on loopback."
    )
    assert invocation.kwargs["workers"] == 1, (
        "The local journal requires one API worker."
    )
    async with testing.ASGIConductor(invocation.args[0]) as conductor:
        response = await conductor.simulate_get("/api/v1/snapshot")
        assert response.json["workspaceId"] == "w1", (
            "The constructed app must use the collector's saved workspace."
        )
        assert response.json["workspaceSlug"] == "leynos", (
            "The workspace selector must survive the CLI boundary."
        )
    assert (tmp_path / "interface-state.key").is_file(), (
        "The server must persist its preference-signing identity."
    )
