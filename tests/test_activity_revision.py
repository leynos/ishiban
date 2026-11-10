"""Execution watermarks distinguish current evidence from stale cache rows."""

import typing as typ

import pytest
from storage_support import (
    EventOptions,
    as_snapshot,
    envelope,
    observed_session,
    opened_store,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_execution_evidence_advances_watermark(tmp_path: Path) -> None:
    """Persisted known state and turn transitions advance the watermark.

    For example, a persisted ``running`` observation is superseded by the
    cursor for a later ``turn.started`` transition.
    """
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        observation_cursor = await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(state="running"),
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId") == observation_cursor, (
            "A persisted known-state observation establishes the execution watermark."
        )

        turn_cursor = await store.ingest(
            envelope(
                2,
                options=EventOptions(
                    event_type="turn.started",
                    user_turn_id="u1",
                    assistant_turn_id="a1",
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId") == turn_cursor, (
            "A turn transition advances the watermark to its journal cursor."
        )
        assert session["latestTurn"] == {
            "userTurnId": "u1",
            "state": "running",
            "assistantTurnId": "a1",
        }, "The watermark advances with the corresponding turn projection."


@pytest.mark.asyncio
async def test_non_evidence_updates_preserve_activity_watermark(
    tmp_path: Path,
) -> None:
    """Metadata, unknown state, and generation changes preserve the watermark."""
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        evidence_cursor = await store.ingest(
            envelope(
                1,
                options=EventOptions(session=observed_session(state="running")),
            ),
            generation,
        )

        await store.ingest(
            envelope(
                2,
                options=EventOptions(
                    session=observed_session(state="unknown", source="metadata"),
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId") == evidence_cursor, (
            "Metadata refreshes preserve the latest execution evidence cursor."
        )

        await store.ingest(
            envelope(
                3,
                options=EventOptions(
                    session=observed_session(state="unknown", source="persisted"),
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId") == evidence_cursor, (
            "Unknown persisted observations cannot invalidate prior execution evidence."
        )

        next_generation = await store.begin_generation()
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert next_generation == generation + 1, (
            "A collector restart advances its generation."
        )
        assert session.get("lastActivityEventId") == evidence_cursor, (
            "Collector generation changes preserve the execution watermark."
        )


@pytest.mark.asyncio
async def test_non_evidence_session_starts_without_watermark(tmp_path: Path) -> None:
    """Metadata-only and unknown sessions do not claim execution evidence."""
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(state="idle", source="metadata"),
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId", 0) == 0, (
            "Metadata-only discovery does not claim execution evidence."
        )

        await store.ingest(
            envelope(
                2,
                options=EventOptions(
                    session=observed_session(state="unknown", source="persisted"),
                ),
            ),
            generation,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        assert session.get("lastActivityEventId", 0) == 0, (
            "An unknown persisted state does not claim execution evidence."
        )
