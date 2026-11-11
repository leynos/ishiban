"""Session and turn projection contracts over observer generations."""

import typing as typ

import pytest
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

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_metadata_observation_preserves_durable_turn_evidence(
    tmp_path: Path,
) -> None:
    """Metadata refresh changes display provenance without erasing outcomes."""
    durable_turn = Turn("u1", "completed", "a1", 840)
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.begin_generation()
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    stream_id="stream-2",
                    session=observed_session(
                        state="idle", latest_turn=durable_turn, active_turns=[]
                    ),
                ),
            ),
            generation=3,
        )
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(
                        state="unknown",
                        source="metadata",
                        latest_turn=None,
                        active_turns=[],
                    )
                ),
            ),
            generation=4,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]

    assert session["state"] == "idle", (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    expected_turn = {
        "userTurnId": "u1",
        "state": "completed",
        "assistantTurnId": "a1",
        "durationMs": 840,
    }
    assert session["latestTurn"] == expected_turn, (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["activeTurns"] == [], (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["source"] == "metadata", (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["freshness"] == "unavailable", (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["lastEvidenceGeneration"] == 3, (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["lastMetadataGeneration"] == 4, (
        "Metadata refresh changes display provenance without erasing outcomes."
    )
    assert session["lastObservedAt"] == 1_700_000_000_001, (
        "Metadata refresh changes display provenance without erasing outcomes."
    )


@pytest.mark.asyncio
async def test_generation_disconnect_preserves_last_known_turn_outcome(
    tmp_path: Path,
) -> None:
    """Collector health changes never synthesize session or turn outcomes."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(
                        state="running",
                        latest_turn=Turn("u1", "running"),
                        active_turns=[Turn("u1", "running")],
                    )
                ),
            ),
            generation=1,
        )
        generation = await store.begin_generation()
        await store.health("disconnected", generation, "observer exited")
        snapshot = as_snapshot(await store.snapshot())
        history = as_events(await store.events(after=0))

    session = snapshot["sessions"][0]
    assert generation == 2, (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert snapshot["collector"]["state"] == "disconnected", (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert session["state"] == "running", (
        "Collector health changes never synthesize session or turn outcomes."
    )
    latest_turn = session["latestTurn"]
    assert latest_turn is not None, (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert latest_turn["state"] == "running", (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert session["activeTurns"][0]["userTurnId"] == "u1", (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert session["lastEvidenceGeneration"] == 1, (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert history[-1]["source"] == "collector", (
        "Collector health changes never synthesize session or turn outcomes."
    )
    assert history[-1]["projection"]["state"] == "disconnected", (
        "Collector health changes never synthesize session or turn outcomes."
    )


@pytest.mark.asyncio
async def test_turn_finish_without_start_and_reopen_same_identity(
    tmp_path: Path,
) -> None:
    """Turn transitions accept missing starts and repeated stable identities."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    event_type="turn.finished",
                    user_turn_id="u1",
                    assistant_turn_id="a1",
                    outcome="failed",
                    duration_ms=230,
                ),
            ),
            generation=1,
        )
        await store.ingest(
            envelope(
                2,
                options=EventOptions(
                    event_type="turn.started",
                    user_turn_id="u1",
                    assistant_turn_id="a2",
                ),
            ),
            generation=1,
        )
        await store.ingest(
            envelope(
                3,
                options=EventOptions(
                    event_type="turn.finished",
                    user_turn_id="u1",
                    assistant_turn_id="a2",
                    outcome="completed",
                    duration_ms=480,
                ),
            ),
            generation=1,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]
        details = as_detail(await store.detail("s1"))

    latest_turn = session["latestTurn"]
    assert latest_turn is not None, (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert latest_turn["state"] == "completed", (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert latest_turn["assistantTurnId"] == "a2", (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert session["activeTurns"] == [], (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert details is not None, (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert len(details["recentEvents"]) == 3, (
        "Turn transitions accept missing starts and repeated stable identities."
    )
    assert details["turns"][0]["state"] == "completed", (
        "Turn transitions accept missing starts and repeated stable identities."
    )


@pytest.mark.asyncio
async def test_removed_session_is_tombstoned_and_history_remains_replayable(
    tmp_path: Path,
) -> None:
    """Removal hides a session from active views without deleting its journal."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(1, options=EventOptions(session=observed_session(state="idle"))),
            generation=1,
        )
        await store.ingest(
            envelope(2, options=EventOptions(event_type="session.removed")),
            generation=1,
        )
        snapshot = as_snapshot(await store.snapshot())
        details = as_detail(await store.detail("s1"))
        history = as_events(await store.events(after=0))

    assert snapshot["sessions"][0]["removed"] is True, (
        "Removal hides a session from active views without deleting its journal."
    )
    assert details is not None, (
        "Removal hides a session from active views without deleting its journal."
    )
    assert details["session"]["removed"] is True, (
        "Removal hides a session from active views without deleting its journal."
    )
    assert (
        len([event for event in history if event["source"] == "lody.observe"]) == 2
    ), "Removal hides a session from active views without deleting its journal."


@pytest.mark.asyncio
async def test_never_persisted_metadata_session_remains_unknown(
    tmp_path: Path,
) -> None:
    """Metadata-only discovery does not assert machine activity or workflow."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(state="idle", source="metadata")
                ),
            ),
            generation=1,
        )
        session = as_snapshot(await store.snapshot())["sessions"][0]

    assert session["state"] == "unknown", (
        "Metadata-only discovery does not assert machine activity or workflow."
    )
    assert session["stage"] == "unclassified", (
        "Metadata-only discovery does not assert machine activity or workflow."
    )
    assert session["lastEvidenceGeneration"] is None, (
        "Metadata-only discovery does not assert machine activity or workflow."
    )
