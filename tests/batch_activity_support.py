"""Shared setup for batch activity request and process-boundary tests."""

import typing as typ

import pytest
from falcon import testing

from ishiban.api import create_app
from ishiban.domain import Envelope, ObservedSession
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    from pathlib import Path


async def post_with_workspace_identity(
    tmp_path: Path, workspace_id: str, route: str
) -> testing.Result:
    """Exercise batch preflight through a real store and Falcon response.

    For example, a huge identity must fail before either endpoint streams.

    Returns
    -------
    testing.Result
        The complete response after store and app shutdown.
    """
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'ishiban.sqlite3'}", workspace_id)
    await store.initialize()
    try:
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                route,
                body='{"sessionIds":["s1"]}',
                headers={"content-type": "application/json"},
            )
    finally:
        await store.close()
    return response


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
