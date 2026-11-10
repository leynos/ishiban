"""Cached runtime outcomes survive real API and collector lifecycle boundaries."""

import dataclasses as dc
import typing as typ
from unittest import mock

import msgspec
import pytest
import pytest_asyncio
from falcon import testing
from storage_support import EventOptions, envelope, observed_session

from ishiban.api import EventsResource, create_app
from ishiban.domain import Turn
from ishiban.lazy_activity import LazyActivity
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


@dc.dataclass(slots=True)
class FailureCase:
    """Own the process identities and read spy for this module's restart cases."""

    url: str
    writer: Store
    generation: int
    lookup: mock.AsyncMock


@pytest_asyncio.fixture
async def collected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> cabc.AsyncIterator[FailureCase]:
    """Collect one failure through Falcon while checking raw journal immutability.

    Yields
    ------
    FailureCase
        Independent collector identity and an already closed first API process.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'journal.sqlite3'}"
    writer = Store(url, "w1")
    await writer.initialize()
    generation = await writer.begin_generation()
    unknown = observed_session(state="unknown", source="metadata")
    await writer.ingest(envelope(1, options=EventOptions(session=unknown)), generation)
    lookup = mock.AsyncMock(
        return_value=observed_session(
            state="idle",
            latest_turn=Turn("failed-turn", "failed", error="Provider failed"),
        )
    )
    monkeypatch.setattr(LazyActivity, "read", lookup)
    baseline = await writer.snapshot()
    events_before = await writer.events(0)
    case = FailureCase(url, writer, generation, lookup)
    try:
        async with testing.ASGIConductor(create_app(Store(url, "w1"))) as conductor:
            assert (await conductor.simulate_get("/api/v1/sessions/s1/activity")).json[
                "session"
            ]["latestTurn"]["state"] == "failed", "The lookup must collect a failure."
            assert await writer.snapshot() == baseline, (
                "The raw journal snapshot stays unchanged."
            )
            assert await writer.events(0) == events_before, (
                "Caching must not append or rewrite events."
            )
        yield case
    finally:
        await case.writer.close()


@pytest.mark.asyncio
async def test_failed_activity_survives_refresh_and_both_process_restarts(
    collected_failure: FailureCase,
) -> None:
    """A fresh API restores failures without another CLI read or journal write."""
    async with testing.ASGIConductor(
        create_app(Store(collected_failure.url, "w1"))
    ) as conductor:
        response = await conductor.simulate_get("/api/v1/snapshot")
        assert response.json["sessions"][0]["latestTurn"] is not None, (
            "A fresh snapshot must retain the on-demand turn outcome."
        )
        assert (
            response.json["sessions"][0]["latestTurn"]["error"] == "Provider failed"
        ), "Refreshing the board must retain the diagnostic."

    await collected_failure.writer.close()
    collected_failure.writer = Store(collected_failure.url, "w1")
    await collected_failure.writer.initialize()
    collected_failure.generation = await collected_failure.writer.begin_generation()
    updated = msgspec.structs.replace(
        observed_session(state="unknown", source="metadata"), title="Updated metadata"
    )
    await collected_failure.writer.ingest(
        envelope(1, options=EventOptions(stream_id="restart", session=updated)),
        collected_failure.generation,
    )
    updated = msgspec.structs.replace(updated, source="persisted", freshness="synced")
    revision = await collected_failure.writer.ingest(
        envelope(2, options=EventOptions(stream_id="restart", session=updated)),
        collected_failure.generation,
    )
    api_store = Store(collected_failure.url, "w1")
    async with testing.ASGIConductor(create_app(api_store)) as conductor:
        response = await conductor.simulate_get("/api/v1/snapshot")
        session = response.json["sessions"][0]
        assert session["state"] == "idle", "Unknown startup state must retain activity."
        assert session["latestTurn"]["state"] == "failed", (
            "Both restarts retain failure."
        )
        assert session["activitySource"] == "lazy", "Keep actual evidence provenance."
        assert session["title"] == "Updated metadata", "Retain newer session metadata."
        assert session["lastEventId"] == revision, (
            "Current collector revisions advance."
        )
        stream = EventsResource(api_store).tail(revision - 1)
        try:
            event = await anext(stream)
            session = msgspec.convert(event.json, type=dict[str, object])
            session = msgspec.convert(session["projection"], type=dict[str, object])
            assert (
                msgspec.convert(session["latestTurn"], type=Turn).state == "failed"
            ), "Live replay must retain the same cached failure as a snapshot."
            assert event.event_id == str(revision), "The cache cannot create a cursor."
        finally:
            await stream.aclose()
    collected_failure.lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_execution_permanently_supersedes_cached_failure(
    collected_failure: FailureCase,
) -> None:
    """A missed known update then unknown state cannot resurrect an old failure."""
    async with testing.ASGIConductor(
        create_app(Store(collected_failure.url, "w1"))
    ) as conductor:
        await collected_failure.writer.ingest(
            envelope(2, options=EventOptions(session=observed_session())),
            collected_failure.generation,
        )
        await collected_failure.writer.ingest(
            envelope(
                3,
                options=EventOptions(
                    session=observed_session(state="unknown", source="persisted")
                ),
            ),
            collected_failure.generation,
        )
        response = await conductor.simulate_get("/api/v1/snapshot")
        current = response.json["sessions"][0]
        assert current["state"] == "unknown", "New execution invalidates cached facts."
        assert current["latestTurn"] is None, "An old cached failure cannot reappear."
        assert current.get("activitySource") is None, "Discard invalidated provenance."
