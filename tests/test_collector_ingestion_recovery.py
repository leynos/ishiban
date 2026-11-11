"""Observer storage retries retain the current event and process ownership."""

import asyncio
import contextlib
import pathlib
import sqlite3
import types
import typing as typ

import pytest
from lody_process_support import tracked_fake_lody_children
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from storage_support import as_snapshot
from test_collector import fake_lody
from test_collector_storage_recovery import RefreshClock

from ishiban import collector as observation
from ishiban.storage import Store
from ishiban.storage.models import source_events
from ishiban.task_ownership import cancel_and_reap

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from ishiban.domain import Envelope


@contextlib.asynccontextmanager
async def _running_observer(
    store: Store, executable: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> cabc.AsyncIterator[
    tuple[asyncio.Task[None], list[tuple[tuple[str, ...], asyncio.subprocess.Process]]]
]:
    """Own a real fixture child and collector task for one ingestion scenario.

    Yields
    ------
    tuple of task and child handles
        The collector and native children observed by the scenario.
    """
    async with contextlib.AsyncExitStack() as cleanup:
        cleanup.push_async_callback(store.close)
        children = await cleanup.enter_async_context(
            tracked_fake_lody_children(monkeypatch, executable)
        )
        collector = observation.Collector(
            store, "leynos", executable=str(executable), github=False
        )
        task = asyncio.create_task(collector.run())
        cleanup.push_async_callback(cancel_and_reap, (task,))
        yield task, children


async def _cancel_and_assert_reaped(
    task: asyncio.Task[None],
    children: list[tuple[tuple[str, ...], asyncio.subprocess.Process]],
) -> None:
    """Prove cancellation returns only after the native observer is reaped."""
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=9)
    observers = [process for argv, process in children if "observe" in argv]
    assert len(observers) == 1, "Retry must retain exactly one owned observer."
    process = observers[0]
    assert process.returncode is not None, "Cancellation must terminate the child."
    assert await asyncio.wait_for(process.wait(), timeout=1) == process.returncode, (
        "Cancellation must reap the child before the collector unwinds."
    )


async def _committed_sequences(store: Store) -> list[int]:
    """Read committed upstream positions independent of public projections.

    Returns
    -------
    list[int]
        Ordered source sequence numbers for the fixture observer stream.
    """
    statement = (
        select(source_events.c.sequence)
        .where(source_events.c.stream_id == "fake")
        .order_by(source_events.c.id)
    )
    async with store._engine.connect() as connection:
        return list((await connection.execute(statement)).scalars().all())


async def _wait_for_running(store: Store) -> None:
    """Observe the event after the fault through the real journal projection."""
    async with asyncio.timeout(3):
        while True:
            snapshot = as_snapshot(await store.snapshot())
            if snapshot["sessions"] and snapshot["sessions"][0]["state"] == "running":
                return
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("fault_after_commit", [False, True])
@pytest.mark.asyncio
async def test_ingestion_retries_same_record_before_reading_next(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fault_after_commit: bool,
) -> None:
    """Both failed writes and uncertain acknowledgements commit each event once."""
    tail = pathlib.Path(__file__).parent / "fixtures" / "lody-observer-activity.jsonl"
    executable = fake_lody(tmp_path, tail.read_text())
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'journal.sqlite3'}", "workspace")
    await store.initialize()
    original_ingest = store.ingest
    attempts: list[int] = []
    first_record_bytes: list[bytes | None] = []

    async def once_faulty_ingest(
        event: Envelope, generation: int, *, raw: bytes | None = None
    ) -> int:
        """Fail one first-record attempt on the selected side of commit.

        Returns
        -------
        int
            The real store cursor after the injected fault is consumed.

        Raises
        ------
        OperationalError
            Once, before or after the real first-event commit.
        """
        attempts.append(event.sequence)
        if event.sequence == 1:
            first_record_bytes.append(raw)
        if event.sequence == 1 and attempts.count(1) == 1:
            if fault_after_commit:
                await original_ingest(event, generation, raw=raw)
            raise OperationalError("ingest", {}, sqlite3.OperationalError())
        return await original_ingest(event, generation, raw=raw)

    monkeypatch.setattr(store, "ingest", once_faulty_ingest)
    async with _running_observer(store, executable, monkeypatch) as (task, children):
        await _wait_for_running(store)
        assert attempts == [1, 1, 2, 3], (
            "The same decoded record must be retried before reading later records."
        )
        assert len(first_record_bytes) == 2, "The first line must have two attempts."
        assert first_record_bytes[0] == first_record_bytes[1], (
            "Retry must reuse the exact raw line for an uncertain first write."
        )
        events = await store.events(after=0)
        observed = [event for event in events if event["source"] == "lody.observe"]
        assert [event["eventType"] for event in observed] == [
            "snapshot",
            "session.changed",
        ], "Both session records must be committed in source order."
        assert await _committed_sequences(store) == [1, 2, 3], (
            "Retry must preserve the original stream order and raw record."
        )
        await _cancel_and_assert_reaped(task, children)


@pytest.mark.asyncio
async def test_persistent_ingest_failure_caps_backoff_and_preserves_cancellation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing stop-health write cannot replace cancellation of the child."""
    executable = fake_lody(tmp_path)
    clock = RefreshClock()
    monkeypatch.setattr(
        observation, "asyncio", types.SimpleNamespace(sleep=clock.sleep)
    )
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'persistent.sqlite3'}", "workspace")
    await store.initialize()
    original_health = store.health
    attempts = 0

    async def failed_ingest(
        _event: Envelope, _generation: int, *, raw: bytes | None = None
    ) -> int:
        """Keep the first event uncommitted for every bounded retry.

        Raises
        ------
        OperationalError
            The durable journal is unavailable.
        """
        nonlocal attempts
        attempts += 1
        await store.current_cursor()
        raise OperationalError("ingest", {}, sqlite3.OperationalError())

    async def failed_stop(state: str, generation: int, error: str | None = None) -> int:
        """Allow initial health, then fail the cancellation health write.

        Returns
        -------
        int
            The original health cursor for non-stopped states.

        Raises
        ------
        OperationalError
            Stopped health cannot be persisted during storage failure.
        """
        if state == "stopped":
            raise OperationalError("health", {}, sqlite3.OperationalError())
        return await original_health(state, generation, error)

    monkeypatch.setattr(store, "ingest", failed_ingest)
    monkeypatch.setattr(store, "health", failed_stop)
    async with _running_observer(store, executable, monkeypatch) as (task, children):
        async with asyncio.timeout(3):
            for expected_delay in (1, 2, 4, 8, 16, 30):
                release = await clock.retries.get()
                assert clock.retry_delays[-1] == expected_delay, (
                    "Ingestion retry must back off to the existing 30-second cap."
                )
                assert not task.done(), "The observer must survive storage retries."
                release.set()
            await clock.retries.get()
        assert clock.retry_delays[-1] == 30, "Backoff must remain capped."
        assert attempts == 7, "One retry attempt is made per released boundary."
        assert not [
            event
            for event in await store.events(after=0)
            if event["source"] == "lody.observe"
        ], "A persistently failed first record must not advance the journal."
        await _cancel_and_assert_reaped(task, children)
