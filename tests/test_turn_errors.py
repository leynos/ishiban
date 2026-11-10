"""Preserve supplied turn diagnostics without inventing missing error evidence."""

import typing as typ

import msgspec
import pytest
from storage_support import as_events, as_snapshot, opened_store

from ishiban.domain import Envelope, ObservedSession, Turn
from ishiban.protocol import StreamPosition, decode_event

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["snapshot", "turn.finished"])
async def test_failed_error_survives_decode_commit_snapshot_and_replay(
    tmp_path: Path, event_type: str
) -> None:
    """Both observer shapes retain the exact failed-turn error in public replay."""
    error = "Provider rejected request.\nTry another model."
    source = Envelope(
        version=1,
        stream_id="errors",
        sequence=1,
        observed_at=1,
        workspace_id="w1",
        type=event_type,
        session_id="s1",
        user_turn_id="u1",
        outcome="failed",
        error=error,
        session=ObservedSession(
            session_id="s1",
            source="persisted",
            latest_turn=Turn("u1", "failed", error=error),
        ),
    )
    decoded = decode_event(msgspec.json.encode(source), "w1", StreamPosition())
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        cursor = await store.ingest(decoded, generation)
        current = as_snapshot(await store.snapshot())["sessions"][0]
        events = as_events(await store.events(cursor - 1))
    latest = current["latestTurn"]
    assert latest is not None, "The failed turn must remain inspectable."
    assert latest["error"] == error, "Snapshot decoding must retain the supplied error."
    assert events[0]["projection"]["latestTurn"] == latest, (
        "Replay must expose the same committed error as the snapshot."
    )


@pytest.mark.asyncio
async def test_error_is_bounded_and_cleared_when_turn_reopens(tmp_path: Path) -> None:
    """A running turn must not inherit the previous failure diagnostic."""
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        failed = Envelope(
            version=1,
            stream_id="errors",
            sequence=1,
            observed_at=1,
            workspace_id="w1",
            type="turn.finished",
            session_id="s1",
            user_turn_id="u1",
            outcome="failed",
            error="x" * 5000,
        )
        await store.ingest(failed, generation)
        latest = as_snapshot(await store.snapshot())["sessions"][0]["latestTurn"]
        assert latest is not None, "A failed turn must have a projection."
        assert len(latest["error"]) == 4096, "Public errors must have a bounded size."
        reopened = msgspec.structs.replace(failed, sequence=2, type="turn.started")
        await store.ingest(reopened, generation)
        latest = as_snapshot(await store.snapshot())["sessions"][0]["latestTurn"]
    assert latest is not None, "Reopening retains the stable turn identity."
    assert "error" not in latest, (
        "Running turns must not display stale failure details."
    )
