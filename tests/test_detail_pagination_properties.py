"""Generated static turn sets verify complete detail-page traversal."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from storage_support import (
    EventOptions,
    as_detail,
    envelope,
    observed_session,
    opened_store,
)

from ishiban.detail_pagination import TURN_PAGE_SIZE, parse_turn_cursor
from ishiban.domain import Turn


@example(group_sizes=[99, 2, 5])
@example(group_sizes=[1, 101, 1])
@example(group_sizes=[100, 100])
@given(
    group_sizes=st.lists(
        st.integers(min_value=1, max_value=140), min_size=2, max_size=3
    )
)
@settings(max_examples=20, deadline=None)
@pytest.mark.asyncio
async def test_static_turn_pages_match_independent_event_and_identity_order(
    group_sizes: list[int],
) -> None:
    """Every retained turn appears once and paging terminates across event groups."""
    with tempfile.TemporaryDirectory() as case_directory:
        async with opened_store(Path(case_directory)) as store:
            generation = await store.begin_generation()
            expected: list[tuple[int, str]] = []
            for sequence, size in enumerate(group_sizes, start=1):
                event_id = await store.ingest(
                    envelope(
                        sequence,
                        options=EventOptions(
                            session=observed_session(
                                active_turns=[
                                    Turn(
                                        user_turn_id=f"g{sequence:02}-u{index:03}",
                                        state="running",
                                    )
                                    for index in range(size - 1, -1, -1)
                                ]
                            )
                        ),
                    ),
                    generation,
                )
                expected.extend(
                    (event_id, f"g{sequence:02}-u{index:03}") for index in range(size)
                )

            actual: list[tuple[int, str]] = []
            after = None
            seen_cursors: set[str] = set()
            for _ in range(len(expected) // TURN_PAGE_SIZE + 2):
                detail = as_detail(await store.detail("s1", after))
                assert detail is not None, "The seeded session must have detail."
                assert len(detail["turns"]) <= TURN_PAGE_SIZE, (
                    "Each page must respect the published turn limit."
                )
                actual.extend(
                    (turn["lastEventId"], turn["userTurnId"])
                    for turn in detail["turns"]
                )
                token = detail["nextTurnCursor"]
                if token is None:
                    break
                assert token not in seen_cursors, (
                    "A cursor cycle must not keep the reader on one page."
                )
                seen_cursors.add(token)
                after = parse_turn_cursor(token, "w1", "s1")
            else:
                pytest.fail("Static pagination must terminate within the page bound.")

    assert actual == sorted(expected), (
        "Concatenated pages must match independent event-ID and turn-ID order."
    )
    assert len(actual) == len(set(actual)), (
        "Every retained turn must appear exactly once."
    )
