"""Session detail exposes all retained turns through bounded pages."""

import base64
import contextlib as ctx
import typing as typ

import msgspec
import pytest
import pytest_asyncio
from falcon import testing
from hypothesis import given
from hypothesis import strategies as st
from storage_support import EventOptions, envelope, observed_session, opened_store

from ishiban.api import create_app
from ishiban.detail_pagination import (
    TurnPageCursor,
    cursor_scope_digest,
    encode_turn_cursor,
    parse_turn_cursor,
)
from ishiban.domain import Turn

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


@ctx.asynccontextmanager
async def _detail_conductor(
    tmp_path: Path, turns: list[Turn]
) -> cabc.AsyncIterator[testing.ASGIConductor]:
    """Serve stored turns; for example, 103 tied turns cross a page boundary.

    Yields
    ------
    testing.ASGIConductor
        A live local API backed by the seeded journal.
    """
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.ingest(
            envelope(
                1, options=EventOptions(session=observed_session(active_turns=turns))
            ),
            generation=1,
        )
        async with testing.ASGIConductor(create_app(store)) as conductor:
            yield conductor


@pytest_asyncio.fixture
async def seeded_detail_conductor(
    tmp_path: Path,
) -> cabc.AsyncIterator[testing.ASGIConductor]:
    """Expose 103 tied turns so a second page is available.

    Yields
    ------
    testing.ASGIConductor
        A live local API with a fully populated first turn page.
    """
    turns = [Turn(user_turn_id=f"u{index:03}", state="running") for index in range(103)]
    async with _detail_conductor(tmp_path, turns) as conductor:
        yield conductor


@pytest.mark.asyncio
async def test_turn_detail_pages_share_a_stable_tiebreaker(
    seeded_detail_conductor: testing.ASGIConductor,
) -> None:
    """Many turns from one event remain reachable exactly once across pages."""
    first = await seeded_detail_conductor.simulate_get("/api/v1/sessions/s1")
    assert first.status_code == 200, "The first detail page must be readable."
    assert len(first.json["turns"]) == 100, (
        "One response must have a fixed upper bound on retained turns."
    )
    cursor = first.json["nextTurnCursor"]
    assert isinstance(cursor, str), (
        "A page with remaining turns must expose a continuation cursor."
    )
    assert cursor, "A page with remaining turns must expose a continuation cursor."
    second = await seeded_detail_conductor.simulate_get(
        f"/api/v1/sessions/s1?turnCursor={cursor}"
    )
    assert second.status_code == 200, "The continuation must be readable."
    assert second.json["nextTurnCursor"] is None, (
        "The final page must not claim another page exists."
    )
    identities = [
        turn["userTurnId"] for page in (first, second) for turn in page.json["turns"]
    ]
    assert identities == [f"u{index:03}" for index in range(103)], (
        "Tied event positions must use turn identity for stable keyset order."
    )


@pytest.mark.asyncio
async def test_detail_rejects_invalid_or_foreign_turn_cursors(
    seeded_detail_conductor: testing.ASGIConductor,
) -> None:
    """Malformed and foreign continuation tokens never become first-page reads."""
    first = await seeded_detail_conductor.simulate_get("/api/v1/sessions/s1")
    cursor = first.json["nextTurnCursor"]
    assert cursor is not None, "The fixture must contain a second page."
    for path in (
        "/api/v1/sessions/s1?turnCursor=%25%25%25",
        f"/api/v1/sessions/s1?turnCursor={'a' * 4097}",
        f"/api/v1/sessions/other?turnCursor={cursor}",
    ):
        response = await seeded_detail_conductor.simulate_get(path)
        assert response.status_code == 400, (
            "Invalid or foreign cursors must not silently restart pagination."
        )
    missing = await seeded_detail_conductor.simulate_get("/api/v1/sessions/missing")
    assert missing.status_code == 404, (
        "A missing session without a cursor must remain not found."
    )


@pytest.mark.asyncio
async def test_long_turn_identifiers_remain_pageable(tmp_path: Path) -> None:
    """A long retained identifier cannot make the next cursor unusable."""
    turns = [
        Turn(user_turn_id=f"u{index:03}{'x' * 5000}", state="running")
        for index in range(101)
    ]
    async with _detail_conductor(tmp_path, turns) as conductor:
        first = await conductor.simulate_get("/api/v1/sessions/s1")
        cursor = first.json["nextTurnCursor"]
        assert isinstance(cursor, str), "The first page must be continued."
        assert len(cursor) < 256, "Cursor size must ignore retained ID length."
        second = await conductor.simulate_get(
            f"/api/v1/sessions/s1?turnCursor={cursor}"
        )
        assert second.status_code == 200, "Long IDs must not prevent paging."
        assert len(second.json["turns"]) == 1, "Every retained turn remains reachable."


@pytest.mark.parametrize(
    "cursor",
    [
        TurnPageCursor(2, cursor_scope_digest("other-workspace", "s1"), 1, 1),
        TurnPageCursor(2, cursor_scope_digest("w1", "other-session"), 1, 1),
        TurnPageCursor(1, cursor_scope_digest("w1", "s1"), 1, 1),
        TurnPageCursor(2, cursor_scope_digest("w1", "s1"), -1, 1),
        TurnPageCursor(2, cursor_scope_digest("w1", "s1"), 1, 0),
        TurnPageCursor(
            2, cursor_scope_digest("w1", "s1"), 1, 9_223_372_036_854_775_808
        ),
    ],
)
def test_turn_cursor_rejects_foreign_or_nonposition_data(
    cursor: TurnPageCursor,
) -> None:
    """A decoded token must remain a valid position for this workspace."""
    with pytest.raises(ValueError, match="Invalid turn cursor"):
        parse_turn_cursor(encode_turn_cursor(cursor), "w1", "s1")


@given(
    workspace_id=st.text(max_size=4097),
    session_id=st.text(max_size=4097),
    event_id=st.integers(min_value=1, max_value=9_223_372_036_854_775_807),
    rank=st.integers(min_value=1, max_value=9_223_372_036_854_775_807),
)
def test_issued_cursor_round_trips_independent_of_scope_length(
    workspace_id: str, session_id: str, event_id: int, rank: int
) -> None:
    """Every issued position has a bounded token and parses for its scope."""
    cursor = TurnPageCursor(
        2, cursor_scope_digest(workspace_id, session_id), event_id, rank
    )
    token = encode_turn_cursor(cursor)
    assert len(token) < 256, "Scope identifiers must not inflate issued tokens."
    assert parse_turn_cursor(token, workspace_id, session_id) == cursor, (
        "Every issued cursor must recover its exact position."
    )


def test_legacy_v1_cursor_is_rejected() -> None:
    """Old user-turn-ID cursors require a fresh first-page request."""
    legacy = {
        "version": 1,
        "workspaceId": "w1",
        "sessionId": "s1",
        "lastEventId": 1,
        "userTurnId": "u1",
    }
    token = base64.urlsafe_b64encode(msgspec.json.encode(legacy)).rstrip(b"=").decode()
    with pytest.raises(ValueError, match="Invalid turn cursor"):
        parse_turn_cursor(token, "w1", "s1")


def test_long_workspace_and_session_ids_keep_a_fixed_cursor() -> None:
    """The scope digest hides identifier length without losing validation."""
    workspace_id = "w" * 5000
    session_id = "s" * 5000
    cursor = TurnPageCursor(2, cursor_scope_digest(workspace_id, session_id), 3, 100)
    token = encode_turn_cursor(cursor)
    assert len(token) < 256, "A long scope must not inflate the token."
    assert parse_turn_cursor(token, workspace_id, session_id) == cursor, (
        "Long scope identifiers must still validate their issued cursor."
    )
