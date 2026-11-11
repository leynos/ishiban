"""Behavioural coverage for provenance across collector generations."""

import asyncio
import dataclasses as dc
import pathlib
import typing as typ

import msgspec
import pytest
from falcon import testing
from lody_process_support import create_fake_lody, tracked_fake_lody_children
from pytest_bdd import given, scenarios, then, when

from ishiban import api
from ishiban.collector import Collector
from ishiban.domain import Envelope, ObservedSession, Turn
from ishiban.storage import Store
from ishiban.task_ownership import cancel_and_reap

if typ.TYPE_CHECKING:
    import collections.abc as cabc

scenarios("features/observation.feature")


@dc.dataclass(slots=True)
class Runtime:
    """One synchronous BDD scenario owns one asynchronous database loop."""

    runner: asyncio.Runner
    store: Store
    database_url: str
    generation: int = 0
    observer_children: list[asyncio.subprocess.Process] = dc.field(default_factory=list)


class PublicSession(msgspec.Struct, rename="camel"):
    """Read only the evidence fields asserted by this scenario."""

    latest_turn: Turn
    last_evidence_generation: int
    last_metadata_generation: int | None


class CollectorGeneration(msgspec.Struct):
    """The collector generation exposed by the public snapshot."""

    generation: int


class PublicSnapshot(msgspec.Struct):
    """The scenario's narrow observable snapshot boundary."""

    collector: CollectorGeneration
    sessions: list[PublicSession]


@pytest.fixture
def runtime(tmp_path: pathlib.Path) -> cabc.Iterator[Runtime]:
    """Own a temporary journal for one scenario.

    Yields
    ------
    Runtime
        A runner and its independent SQLite store.
    """
    with asyncio.Runner() as runner:
        database_url = f"sqlite+aiosqlite:///{tmp_path / 'bdd.sqlite3'}"
        store = Store(database_url, "workspace")
        runner.run(store.initialize())
        runtime = Runtime(runner, store, database_url)
        try:
            yield runtime
        finally:
            runner.run(runtime.store.close())


@given("a fresh observation journal")
def fresh_journal(runtime: Runtime) -> None:
    """Begin with an initialized journal before any collector owns a source."""
    snapshot = msgspec.convert(
        runtime.runner.run(runtime.store.snapshot()), type=PublicSnapshot
    )
    assert snapshot.collector.generation == 0, (
        "The real collector must create the scenario's first generation."
    )


async def _collect_snapshot(
    store: Store, executable: pathlib.Path, *, generation: int, marker: str
) -> None:
    """Wait for one real observer snapshot, then cancel and reap its child."""
    task = asyncio.create_task(
        Collector(store, "leynos", executable=str(executable), github=False).run()
    )
    try:
        async with asyncio.timeout(3):
            while True:
                snapshot = await store.snapshot()
                sessions = typ.cast("list[dict[str, object]]", snapshot["sessions"])
                collector = typ.cast("dict[str, object]", snapshot["collector"])
                session = sessions[0] if sessions else {}
                if (
                    collector["generation"] == generation
                    and session.get(marker) == generation
                ):
                    return
                await asyncio.sleep(0.01)
    finally:
        async with asyncio.timeout(9):
            await cancel_and_reap((task,))
        assert task.cancelled(), "Collector shutdown must reap its observer task."


def _observer_frame(
    stream_id: str, observed_at: int, session: ObservedSession
) -> bytes:
    """Encode one workspace-bound snapshot for the native observer fixture.

    For example, a second stream starts sequence one after the first child was
    reaped, so the collector must reconcile it as a new source generation.

    Returns
    -------
    bytes
        One complete version-one JSONL frame for the isolated workspace.
    """
    return (
        msgspec.json.encode(
            Envelope(
                version=1,
                stream_id=stream_id,
                sequence=1,
                observed_at=observed_at,
                workspace_id="workspace",
                type="snapshot",
                session_id="session",
                session=session,
            )
        )
        + b"\n"
    )


async def _reconcile_restart(
    runtime: Runtime, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run two native observers against one reopened journal."""
    completed = ObservedSession(
        session_id="session",
        machine_id="machine",
        state="idle",
        source="persisted",
        freshness="synced",
        latest_turn=Turn(user_turn_id="turn", state="completed"),
    )
    first = _observer_frame("first", 1, completed)
    metadata = ObservedSession(
        session_id="session",
        machine_id="machine",
        source="metadata",
        freshness="synced",
    )
    second = _observer_frame("second", 2, metadata)
    stream_path = pathlib.Path(tmp_path, "observer.jsonl")
    executable, _call_log = create_fake_lody(
        tmp_path,
        f"payload = pathlib.Path({str(stream_path)!r}).read_text()",
        linger_after_output=120,
    )
    async with tracked_fake_lody_children(monkeypatch, executable) as children:
        await asyncio.to_thread(stream_path.write_bytes, first)
        await _collect_snapshot(
            runtime.store, executable, generation=1, marker="lastEvidenceGeneration"
        )
        assert len(children) == 1, "The first collector must own one observer."
        assert children[0][1].returncode is not None, (
            "The first observer child must be reaped before the restart."
        )
        runtime.generation = 1
        await runtime.store.close()
        runtime.store = Store(runtime.database_url, "workspace")
        await runtime.store.initialize()
        await asyncio.to_thread(stream_path.write_bytes, second)
        await _collect_snapshot(
            runtime.store, executable, generation=2, marker="lastMetadataGeneration"
        )
        expected_command = (
            "session",
            "observe",
            "--workspace",
            "leynos",
            "--all",
            "--jsonl",
            "--follow",
        )
        assert [command[1:] for command, _ in children] == [expected_command] * 2, (
            "Both generations must use only the read-only observer command."
        )
        runtime.observer_children = [process for _, process in children]


@when("a persisted completion is followed by a metadata-only restart")
def reconcile_restart(
    runtime: Runtime, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run and reap two read-only observer processes across a journal reopen."""
    runtime.runner.run(_reconcile_restart(runtime, tmp_path, monkeypatch))


@then("the completion is retained as evidence from the earlier generation")
def retained_completion(runtime: Runtime) -> None:
    """Assert native cleanup and the final Falcon projection together."""
    assert len(runtime.observer_children) == 2, (
        "Both generations must run an owned native observer child."
    )
    assert all(
        process.returncode is not None for process in runtime.observer_children
    ), "Both observer children must be reaped before public inspection."

    async def public_snapshot() -> PublicSnapshot:
        """Read the same reopened journal through the real Falcon snapshot route.

        Returns
        -------
        PublicSnapshot
            The bounded public response after both collector generations.
        """
        async with testing.ASGIConductor(api.create_app(runtime.store)) as conductor:
            response = await conductor.simulate_get("/api/v1/snapshot")
        assert response.status_code == 200, "The public snapshot must remain readable."
        return msgspec.convert(response.json, type=PublicSnapshot)

    snapshot = runtime.runner.run(public_snapshot())
    assert snapshot.sessions[0].latest_turn.state == "completed", (
        "Metadata after restart must retain the proven completion."
    )
    assert snapshot.sessions[0].last_evidence_generation == runtime.generation, (
        "Metadata cannot advance the durable evidence generation."
    )
    assert snapshot.collector.generation == 2, (
        "The second collector must own a new durable generation."
    )
    assert snapshot.sessions[0].last_metadata_generation == 2, (
        "The second metadata snapshot must commit, not merely start a generation."
    )
