"""Slow activity reads may survive metadata replay, but never new execution."""

import typing as typ

import pytest
from storage_support import EventOptions, envelope, observed_session, opened_store

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("has_new_execution", [False, True])
async def test_activity_rebase_preserves_execution_barrier(
    tmp_path: Path, *, has_new_execution: bool
) -> None:
    """Metadata replay preserves a read while newer execution invalidates it."""
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        metadata = observed_session(state="unknown", source="metadata")
        await store.ingest(
            envelope(1, options=EventOptions(session=metadata)), generation
        )
        previous = await store.session_projection("s1")
        assert previous is not None, "The session must exist before its lazy read."
        late = {**previous, "state": "idle", "activitySource": "lazy"}
        if has_new_execution:
            await store.ingest(
                envelope(2, options=EventOptions(session=observed_session())),
                generation,
            )
        await store.ingest(
            envelope(3, options=EventOptions(session=metadata)), generation
        )
        baseline = await store.snapshot()
        restored = await store.remember_activity(late)
        if has_new_execution:
            assert restored is None, "New execution must invalidate an older read."
        else:
            assert restored is not None, "Metadata replay must not discard a slow read."
            assert restored["state"] == "idle", "The runtime result must survive."
            current = await store.session_projection("s1")
            assert current is not None, "The current catalogue must remain available."
            assert restored["lastEventId"] == current["lastEventId"], (
                "Rebased activity must use the current metadata revision."
            )
        assert await store.snapshot() == baseline, (
            "Enrichment must leave the journal intact."
        )
