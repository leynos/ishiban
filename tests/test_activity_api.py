"""On-demand activity enriches responses without changing the durable journal."""

import typing as typ
from unittest import mock

import pytest
from falcon import testing
from storage_support import (
    EventOptions,
    as_snapshot,
    envelope,
    observed_session,
    opened_store,
)

from ishiban import activity_api
from ishiban.activity_api import ActivityResolutionOptions, resolve_activity
from ishiban.api import create_app
from ishiban.domain import ObservedSession, Turn
from ishiban.lazy_activity import LazyActivity

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_lazy_activity_keeps_the_journal_cursor_and_evidence_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An on-demand read changes only the HTTP response, not persisted activity."""
    lookup = mock.AsyncMock(
        return_value=ObservedSession(
            session_id="s1",
            source="persisted",
            freshness="synced",
            state="running",
            latest_turn=Turn("u1", "running"),
        )
    )
    monkeypatch.setattr(LazyActivity, "read", lookup)
    monkeypatch.setattr(activity_api.time, "time_ns", lambda: 1_700_000_000_456_999_999)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(
                        state="unknown",
                        source="metadata",
                    )
                ),
            ),
            generation,
        )
        baseline = as_snapshot(await store.snapshot())
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get("/api/v1/sessions/s1/activity")
            after = as_snapshot(await store.snapshot())
            projected = response.json["session"]
            assert projected["title"] == baseline["sessions"][0]["title"], (
                "An activity lookup must not erase catalogue metadata."
            )
            assert projected["state"] == "running", (
                "The lazy result must resolve activity."
            )
            assert projected["activitySource"] == "lazy", (
                "Lazy evidence must be labelled."
            )
            assert projected["lastObservedAt"] == 1_700_000_000_456, (
                "The default clock must stamp accepted reads in epoch milliseconds."
            )
            assert projected["lastEvidenceGeneration"] is None, (
                "An API read must not invent a durable collector generation."
            )
            assert projected["lastEventId"] == baseline["sessions"][0]["lastEventId"], (
                "Lazy enrichment must preserve the mark's event revision."
            )
            assert after == baseline, (
                "The reader must leave every journal fact untouched."
            )
        lookup.assert_awaited_once_with(
            "s1", baseline["sessions"][0].get("lastActivityEventId", 0)
        )


@pytest.mark.asyncio
async def test_injected_epoch_clock_persists_exact_milliseconds_without_journal_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fixed observation timestamp survives sidecar reopen without journal writes."""
    lookup = mock.AsyncMock(
        return_value=ObservedSession(
            session_id="s1",
            source="persisted",
            freshness="synced",
            state="running",
        )
    )
    monkeypatch.setattr(LazyActivity, "read", lookup)
    clock_ns = mock.Mock(return_value=1_700_000_000_123_999_999)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(state="unknown", source="metadata")
                ),
            ),
            generation,
        )
        baseline = await store.snapshot()
        events_before = await store.events(0)
        result = await resolve_activity(
            store,
            LazyActivity("w1", "w1"),
            "s1",
            options=ActivityResolutionOptions(clock_ns=clock_ns),
        )
        assert result is not None, "A valid persisted read must resolve activity."
        assert result["lastObservedAt"] == 1_700_000_000_123, (
            "The injected epoch nanoseconds must be truncated to milliseconds."
        )
        assert await store.snapshot() == baseline, (
            "Lazy activity must not change the durable snapshot or cursor."
        )
        assert await store.events(0) == events_before, (
            "Lazy activity must not append a source journal event."
        )
    lookup.assert_awaited_once()
    clock_ns.assert_called_once_with()

    async with opened_store(tmp_path) as store:
        previous = await store.session_projection("s1")
        assert previous is not None, "The journal session must survive reopening."
        restored = (await store.restore_activity([previous]))[0]
        assert restored["lastObservedAt"] == 1_700_000_000_123, (
            "The same timestamp must survive a sidecar reopen."
        )


@pytest.mark.asyncio
async def test_unavailable_activity_does_not_read_injected_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable observer result has no new observation time to record."""
    monkeypatch.setattr(LazyActivity, "read", mock.AsyncMock(return_value=None))
    clock_ns = mock.Mock(return_value=1_700_000_000_123_999_999)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=observed_session(state="unknown", source="metadata")
                ),
            ),
            generation,
        )
        assert (
            await resolve_activity(
                store,
                LazyActivity("w1", "w1"),
                "s1",
                options=ActivityResolutionOptions(clock_ns=clock_ns),
            )
            is None
        ), "An unavailable read must remain unresolved."
    clock_ns.assert_not_called()


@pytest.mark.asyncio
async def test_known_and_missing_sessions_do_not_open_observers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only known identities with unknown activity may trigger on-demand reads."""
    lookup = mock.AsyncMock()
    monkeypatch.setattr(LazyActivity, "read", lookup)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(
                1,
                options=EventOptions(
                    session=ObservedSession(
                        session_id="s1",
                        title="t" * 1_100_000,
                        state="idle",
                        source="persisted",
                        freshness="synced",
                    )
                ),
            ),
            generation,
        )
        async with testing.ASGIConductor(create_app(store)) as conductor:
            known = await conductor.simulate_get("/api/v1/sessions/s1/activity")
            fallback = await conductor.simulate_get(
                "/api/v1/sessions/s1/activity?includeKnown=true"
            )
            missing = await conductor.simulate_get("/api/v1/sessions/absent/activity")
        assert known.json["session"] is None, "Known activity needs no enrichment."
        assert fallback.json["session"]["state"] == "idle", (
            "The explicit fallback must return current known evidence without Lody."
        )
        assert len(fallback.json["session"]["title"]) == 1_100_000, (
            "A known session too large for a batch frame must retain its title."
        )
        assert missing.status_code == 404, "Unknown identities must not reach Lody."
        lookup.assert_not_awaited()
