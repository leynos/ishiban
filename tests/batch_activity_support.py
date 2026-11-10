"""Shared setup for batch activity request and process-boundary tests."""

import typing as typ

import pytest

from ishiban.domain import Envelope, ObservedSession

if typ.TYPE_CHECKING:
    from ishiban.storage import Store


async def seed_unknown_sessions(store: Store, session_ids: list[str]) -> None:
    """Add metadata-only rows that are eligible for lazy activity reads.

    For example, ``["s1", "s2"]`` creates two unknown identities without
    asserting that either session is running.
    """
    generation = await store.begin_generation()
    for sequence, session_id in enumerate(session_ids, start=1):
        await store.ingest(
            Envelope(
                version=1,
                stream_id="batch-test",
                sequence=sequence,
                observed_at=1_700_000_000_000 + sequence,
                workspace_id=store.workspace_id,
                type="snapshot",
                session_id=session_id,
                session=ObservedSession(
                    session_id=session_id,
                    machine_id="machine-1",
                    title=f"Session {session_id}",
                    state="unknown",
                    source="metadata",
                ),
            ),
            generation,
        )


async def remember_idle_activity(store: Store, session_id: str) -> dict[str, object]:
    """Persist one lazy cache hit without changing its durable projection.

    For example, a metadata-only ``s1`` row is restored as cached ``idle``.

    Returns
    -------
    dict[str, object]
        The cache-restored runtime projection.
    """
    projection = await store.session_projection(session_id)
    if projection is None:
        pytest.fail("A cached test session must exist in the journal.")
    projection.update({
        "state": "idle",
        "source": "persisted",
        "freshness": "synced",
        "latestTurn": None,
        "activeTurns": [],
    })
    cached = await store.remember_activity(projection)
    if cached is None:
        pytest.fail("Valid runtime activity should enter the sidecar cache.")
    return cached
