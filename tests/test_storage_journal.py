"""Journal persistence, replay ordering and SQLite isolation contracts."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select, text
from storage_support import (
    EventOptions,
    as_detail,
    as_events,
    as_snapshot,
    envelope,
    observed_session,
    opened_store,
)

from ishiban.domain import Turn
from ishiban.storage.models import source_events


@pytest.mark.asyncio
async def test_duplicate_stream_sequence_returns_original_cursor_after_restart(
    tmp_path: Path,
) -> None:
    """A duplicate Lody identity never replaces committed evidence."""
    first = envelope(1, options=EventOptions(session=observed_session(state="running")))
    duplicate = envelope(
        1, options=EventOptions(session=observed_session(state="idle"))
    )

    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        cursor = await store.ingest(first, generation=1)
        assert await store.ingest(duplicate, generation=1) == cursor, (
            "A duplicate Lody identity never replaces committed evidence."
        )

    async with opened_store(tmp_path) as restarted:
        snapshot = as_snapshot(await restarted.snapshot())
        history = as_events(await restarted.events(after=0))

    assert snapshot["cursor"] == cursor, (
        "A duplicate Lody identity never replaces committed evidence."
    )
    assert snapshot["sessions"][0]["state"] == "running", (
        "A duplicate Lody identity never replaces committed evidence."
    )
    observed_events = [event for event in history if event["source"] == "lody.observe"]
    assert [event["cursor"] for event in observed_events] == [cursor], (
        "A duplicate Lody identity never replaces committed evidence."
    )
    assert observed_events[0]["projection"]["lastEventId"] == cursor, (
        "A duplicate Lody identity never replaces committed evidence."
    )


@pytest.mark.asyncio
async def test_journal_replay_keeps_the_projection_from_each_commit(
    tmp_path: Path,
) -> None:
    """Replay returns each immutable post-event projection in cursor order."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        first_cursor = await store.ingest(
            envelope(
                1, options=EventOptions(session=observed_session(state="running"))
            ),
            generation=1,
        )
        first_projection = next(
            event["projection"]
            for event in as_events(await store.events(after=0))
            if event["source"] == "lody.observe"
        )
        second_cursor = await store.ingest(
            envelope(
                2, options=EventOptions(session=observed_session(state="waiting"))
            ),
            generation=1,
        )
        history = as_events(await store.events(after=0))
        snapshot = as_snapshot(await store.snapshot())

    assert first_cursor < second_cursor, (
        "Replay returns each immutable post-event projection in cursor order."
    )
    observed_events = [event for event in history if event["source"] == "lody.observe"]
    assert observed_events[0]["projection"] == first_projection, (
        "Replay returns each immutable post-event projection in cursor order."
    )
    assert observed_events[0]["projection"]["state"] == "running", (
        "Replay returns each immutable post-event projection in cursor order."
    )
    assert observed_events[1]["projection"]["state"] == "waiting", (
        "Replay returns each immutable post-event projection in cursor order."
    )
    assert snapshot["cursor"] == second_cursor, (
        "Replay returns each immutable post-event projection in cursor order."
    )
    assert snapshot["sessions"][0]["lastEventId"] == second_cursor, (
        "Replay returns each immutable post-event projection in cursor order."
    )


@pytest.mark.asyncio
async def test_raw_validated_event_is_retained_but_not_exposed_in_detail(
    tmp_path: Path,
) -> None:
    """The private journal retains unknown v1 fields outside public detail."""
    raw_event = (
        b'{"version":1,"streamId":"stream-1","sequence":1,'
        b'"observedAt":1700000000001,"workspaceId":"w1",'
        b'"type":"session.changed","sessionId":"s1",'
        b'"session":{"sessionId":"s1","machineId":"m1",'
        b'"title":"Compiler repair","archived":false,"state":"running",'
        b'"source":"persisted","freshness":"synced",'
        b'"latestTurn":null,"activeTurns":[]},"unknownV1":"retained"}\n'
    )
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(session=observed_session(state="running")),
            ),
            generation=1,
            raw=raw_event,
        )
        async with store._engine.connect() as connection:
            stored_payload = await connection.scalar(
                select(source_events.c.payload_json).where(
                    source_events.c.session_id == "s1"
                )
            )
        detail = as_detail(await store.detail("s1"))

    assert stored_payload == raw_event.decode("utf-8"), (
        "The private journal retains unknown v1 fields outside public detail."
    )
    assert detail is not None, (
        "The private journal retains unknown v1 fields outside public detail."
    )
    assert "payload" not in detail["recentEvents"][0], (
        "The private journal retains unknown v1 fields outside public detail."
    )


@pytest.mark.asyncio
async def test_snapshot_and_journal_projections_share_committed_cursors(
    tmp_path: Path,
) -> None:
    """A snapshot cursor bounds every projection it returns."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(
                        state="running",
                        latest_turn=Turn("u1", "running", "a1"),
                        active_turns=[Turn("u1", "running", "a1")],
                    )
                ),
            ),
            generation=1,
        )
        snapshot = as_snapshot(await store.snapshot())
        history = as_events(await store.events(after=0))

    cursor = snapshot["cursor"]
    assert all(session["lastEventId"] <= cursor for session in snapshot["sessions"]), (
        "A snapshot cursor bounds every projection it returns."
    )
    assert all(event["cursor"] <= cursor for event in history), (
        "A snapshot cursor bounds every projection it returns."
    )
    assert all(
        event["projection"].get("lastEventId", event["cursor"]) == event["cursor"]
        for event in history
    ), "A snapshot cursor bounds every projection it returns."


def test_replay_cursor_order_holds_for_generated_event_sequences(
    tmp_path: Path,
) -> None:
    """Generated state changes retain strictly increasing local cursors."""

    @given(
        st.lists(
            st.sampled_from(["running", "waiting", "idle"]), min_size=1, max_size=12
        )
    )
    @settings(max_examples=12, deadline=None)
    def assert_replay(states: list[str]) -> None:
        """Give each generated sequence an isolated database and event loop."""
        with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
            asyncio.run(_assert_replay_for_states(Path(directory), states))

    assert_replay()


async def _assert_replay_for_states(directory: Path, states: list[str]) -> None:
    """Check immutable event projections and unique ordered journal positions."""
    async with opened_store(directory) as store:
        await store.begin_generation()
        for sequence, state in enumerate(states, start=1):
            await store.ingest(
                envelope(
                    sequence,
                    options=EventOptions(session=observed_session(state=state)),
                ),
                generation=1,
            )
        history = as_events(await store.events(after=0))

    observed_events = [event for event in history if event["source"] == "lody.observe"]
    cursors = [event["cursor"] for event in observed_events]
    assert cursors == sorted(set(cursors)), (
        "Check immutable event projections and unique ordered journal positions."
    )
    assert all(
        event["projection"]["lastEventId"] == event["cursor"]
        for event in observed_events
    ), "Check immutable event projections and unique ordered journal positions."


@pytest.mark.asyncio
async def test_sqlite_uses_wal_busy_timeout_foreign_keys_and_repeatable_reads(
    tmp_path: Path,
) -> None:
    """SQLite must support concurrent readers during writer commits."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        async with store._engine.connect() as reader:
            transaction = await reader.begin()
            await reader.execute(select(source_events.c.id))
            busy_timeout = await reader.scalar(text("PRAGMA busy_timeout"))
            assert isinstance(busy_timeout, int), (
                "SQLite must support concurrent readers during writer commits."
            )
            assert busy_timeout >= 1000, (
                "SQLite must support concurrent readers during writer commits."
            )
            assert await reader.scalar(text("PRAGMA foreign_keys")) == 1, (
                "SQLite must support concurrent readers during writer commits."
            )
            journal_mode = await reader.scalar(text("PRAGMA journal_mode"))

            await store.ingest(
                envelope(1, options=EventOptions(session=observed_session())),
                generation=1,
            )
            count_in_original_snapshot = await reader.scalar(
                sa.select(sa.func.count()).select_from(source_events)
            )
            await transaction.rollback()

        assert journal_mode == "wal", (
            "SQLite must support concurrent readers during writer commits."
        )
        assert count_in_original_snapshot == 1, (
            "SQLite must support concurrent readers during writer commits."
        )
        assert (await store.snapshot())["cursor"] == 2, (
            "SQLite must support concurrent readers during writer commits."
        )
