"""Public session views bound active-turn previews without pruning history."""

import json
import typing as typ
from unittest import mock

import pytest
import storage_support as support
from batch_activity_support import seed_unknown_sessions
from falcon import testing

from ishiban import api
from ishiban.domain import ObservedSession, Turn
from ishiban.lazy_activity import LazyActivity
from ishiban.public_projection import public_session

if typ.TYPE_CHECKING:
    from pathlib import Path


def assert_bounded_turn_preview(session: dict[str, object]) -> None:
    """Assert a 105-turn public view retains a bounded complete-set summary."""
    active_turns = typ.cast("list[dict[str, object]]", session["activeTurns"])
    latest_turn = typ.cast("dict[str, object]", session["latestTurn"])
    assert len(active_turns) == 100, "Public active turns need a fixed preview bound."
    assert session["activeTurnCount"] == 105, "Count the full active set."
    assert session["activeTurnsTruncated"] is True, "Disclose hidden active turns."
    assert isinstance(session["activeTurnsRevision"], str), (
        "Expose the full-set semantic revision."
    )
    assert latest_turn["error"] == "failure text", (
        "Keep the exact latest error outside the active-turn preview."
    )


@pytest.mark.asyncio
async def test_public_session_views_bound_active_turns_and_retain_history(
    tmp_path: Path,
) -> None:
    """Snapshot, detail and replay expose a preview while storage stays complete."""
    turns = [
        Turn(f"u{index:03}", "pending" if index % 2 else "unknown")
        for index in range(105)
    ]
    async with support.opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            support.envelope(
                1,
                options=support.EventOptions(
                    session=support.observed_session(
                        state="running",
                        latest_turn=Turn("u104", "failed", error="failure text"),
                        active_turns=turns,
                    )
                ),
            ),
            generation=1,
        )
        private = support.as_snapshot(await store.snapshot())
        assert len(private["sessions"][0]["activeTurns"]) == 105, (
            "Public shaping must not prune the materialized session."
        )
        private_event = next(
            row
            for row in support.as_events(await store.events(0))
            if row.get("sessionId") == "s1"
        )
        assert len(private_event["projection"]["activeTurns"]) == 105, (
            "Public shaping must not truncate committed replay evidence."
        )
        async with testing.ASGIConductor(api.create_app(store)) as conductor:
            snapshot = await conductor.simulate_get("/api/v1/snapshot")
            detail = await conductor.simulate_get("/api/v1/sessions/s1")
            next_page = await conductor.simulate_get(
                f"/api/v1/sessions/s1?turnCursor={detail.json['nextTurnCursor']}"
            )
            stream = api.EventsResource(store).tail(private_event["cursor"] - 1)
            try:
                event = await anext(stream)
            finally:
                await stream.aclose()
        event_body = typ.cast("dict[str, dict[str, object]]", event.json)
        for session in (
            snapshot.json["sessions"][0],
            detail.json["session"],
            event_body["projection"],
        ):
            assert_bounded_turn_preview(typ.cast("dict[str, object]", session))
            assert session["state"] == "running", (
                "Preview selection must preserve full-session state."
            )
        assert snapshot.json["sessions"][0]["activeTurns"][0]["state"] == "unknown", (
            "Unknown active turns must remain eligible for the preview."
        )
        assert len(detail.json["turns"]) == 100, (
            "Historical turns need a bounded first detail page."
        )
        assert detail.json["nextTurnCursor"] is not None, (
            "Retained history beyond the first page needs a continuation."
        )
        assert len(next_page.json["turns"]) == 5, (
            "The next page must expose the remaining retained turns."
        )
        assert next_page.json["nextTurnCursor"] is None, (
            "The final detail page must end the continuation chain."
        )
        assert {
            turn["userTurnId"]
            for page in (detail, next_page)
            for turn in page.json["turns"]
        } == {f"u{index:03}" for index in range(105)}, (
            "Every retained turn must remain reachable across pages."
        )


def test_hidden_turn_facts_change_revision_without_reordering_noise() -> None:
    """A hidden same-count error changes the digest; input order does not."""
    turns = [{"userTurnId": f"u{index:03}", "state": "pending"} for index in range(105)]
    original = public_session({"activeTurns": turns})
    reordered = public_session({"activeTurns": list(reversed(turns))})
    changed_turns = [dict(turn) for turn in turns]
    changed_turns[-1]["error"] = "new failure"
    changed = public_session({"activeTurns": changed_turns})
    assert original["activeTurns"] == reordered["activeTurns"], (
        "Preview order must not depend on observer input order."
    )
    assert original["activeTurnsRevision"] == reordered["activeTurnsRevision"], (
        "Reordering the same full set is not new runtime evidence."
    )
    assert original["activeTurns"] == changed["activeTurns"], (
        "A changed hidden turn must stay hidden in the capped preview."
    )
    assert original["activeTurnCount"] == changed["activeTurnCount"] == 105, (
        "A hidden error does not change the number of active turns."
    )
    assert original["activeTurnsRevision"] != changed["activeTurnsRevision"], (
        "The full-set revision must detect a same-count hidden error."
    )


@pytest.mark.asyncio
async def test_lazy_activity_frames_bound_full_cached_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single and batched lazy frames cap only their public response copies."""
    turns = [Turn(f"u{index:03}", "waiting") for index in range(105)]
    lookup = mock.AsyncMock(
        return_value=ObservedSession(
            session_id="s1",
            state="waiting",
            source="persisted",
            freshness="synced",
            latest_turn=Turn("u104", "failed", error="failure text"),
            active_turns=turns,
        )
    )
    monkeypatch.setattr(LazyActivity, "read", lookup)
    async with support.opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1"])
        async with testing.ASGIConductor(api.create_app(store)) as conductor:
            single = await conductor.simulate_get("/api/v1/sessions/s1/activity")
            batch = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["s1"]}),
                headers={"content-type": "application/json"},
            )
            snapshot = await conductor.simulate_get("/api/v1/snapshot")
            current = await store.session_projection("s1")
            assert current is not None, "The cached session must remain stored."
            cached = await store.restore_activity([current])
        frame = json.loads(batch.content.splitlines()[0])
        for session in (
            single.json["session"],
            frame["session"],
            snapshot.json["sessions"][0],
        ):
            assert_bounded_turn_preview(typ.cast("dict[str, object]", session))
        assert len(typ.cast("list[object]", cached[0]["activeTurns"])) == 105, (
            "Public lazy frames must not shrink the persisted activity sidecar."
        )
        lookup.assert_awaited_once()
