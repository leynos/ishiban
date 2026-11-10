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
                    session=observed_session(
                        state="idle",
                        source="persisted",
                    )
                ),
            ),
            generation,
        )
        async with testing.ASGIConductor(create_app(store)) as conductor:
            known = await conductor.simulate_get("/api/v1/sessions/s1/activity")
            missing = await conductor.simulate_get("/api/v1/sessions/absent/activity")
        assert known.json["session"] is None, "Known activity needs no enrichment."
        assert missing.status_code == 404, "Unknown identities must not reach Lody."
        lookup.assert_not_awaited()
