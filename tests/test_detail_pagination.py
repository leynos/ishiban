"""Session detail exposes all retained turns through bounded pages."""

import typing as typ

import pytest
import pytest_asyncio
from falcon import testing
from storage_support import EventOptions, envelope, observed_session, opened_store

from ishiban.api import create_app
from ishiban.detail_pagination import (
    TurnPageCursor,
    encode_turn_cursor,
    parse_turn_cursor,
)
from ishiban.domain import Turn

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


@pytest_asyncio.fixture
async def seeded_detail_conductor(
    tmp_path: Path,
) -> cabc.AsyncIterator[testing.ASGIConductor]:
    """Expose 103 tied turns; for example, every test can request page two.

    Yields
    ------
    testing.ASGIConductor
        A live local API backed by the seeded journal.
    """
    turns = [Turn(user_turn_id=f"u{index:03}", state="running") for index in range(103)]
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


@pytest.mark.parametrize(
    "cursor",
    [
        TurnPageCursor(1, "other-workspace", "s1", 1, "u1"),
        TurnPageCursor(2, "w1", "s1", 1, "u1"),
        TurnPageCursor(1, "w1", "s1", -1, "u1"),
        TurnPageCursor(1, "w1", "s1", 1, ""),
    ],
)
def test_turn_cursor_rejects_foreign_or_nonposition_data(
    cursor: TurnPageCursor,
) -> None:
    """A decoded token must remain a valid position for this workspace."""
    with pytest.raises(ValueError, match="Invalid turn cursor"):
        parse_turn_cursor(encode_turn_cursor(cursor), "w1", "s1")
