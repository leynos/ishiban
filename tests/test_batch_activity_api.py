"""Bounded NDJSON activity batches resolve visible sessions independently."""

import asyncio
import json
import typing as typ

import pytest
from falcon import testing

from ishiban.api import create_app
from ishiban.batch_activity_api import BatchSessionActivityResource
from ishiban.domain import Envelope, ObservedSession
from ishiban.lazy_activity import LazyActivity
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    from pathlib import Path


async def _seed_unknown_sessions(store: Store, session_ids: list[str]) -> None:
    """Add metadata-only rows so each requested identity exists in the journal.

    For example, ``['s1', 's2']`` makes two sessions eligible for on-demand
    activity reads without claiming that either one is running.
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


async def _remember_idle_activity(store: Store, session_id: str) -> dict[str, object]:
    """Store one runtime cache hit without changing its durable projection.

    For example, a metadata-only ``s1`` row is restored as cached ``idle``.

    Returns
    -------
    dict[str, object]
        The cache-restored runtime projection.
    """
    projection = await store.session_projection(session_id)
    assert projection is not None, "A cached test session must exist in the journal."
    projection.update({
        "state": "idle",
        "source": "persisted",
        "freshness": "synced",
        "latestTurn": None,
        "activeTurns": [],
    })
    cached = await store.remember_activity(projection)
    assert cached is not None, "Valid runtime activity should enter the sidecar cache."
    return cached


class _BlockingActivity(LazyActivity):
    """Expose cancellation of a waiter owned by the batch response stream."""

    def __init__(self) -> None:
        """Create request-waiter lifecycle signals for the streaming test."""
        super().__init__("w1", "w1")
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self._release = asyncio.Event()

    async def read(self, session_id: str, revision: int) -> ObservedSession | None:
        """Wait until the response stream cancels the pending lookup.

        Returns
        -------
        ObservedSession or None
            ``None`` after release; normally cancellation stops this wait.

        Raises
        ------
        asyncio.CancelledError
            When the response stream closes while this lookup is pending.
        """
        _ = session_id, revision
        self.started.set()
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return None


@pytest.mark.asyncio
async def test_batch_route_returns_unique_frames_for_each_completed_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The batch route emits one workspace-bound frame per unique input ID."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'batch.sqlite3'}", "w1")
    await store.initialize()
    await _seed_unknown_sessions(store, ["s1", "s2"])
    await _remember_idle_activity(store, "s1")
    calls: list[str] = []

    async def read(
        _activity: LazyActivity, session_id: str, _revision: int
    ) -> ObservedSession | None:
        """Return independent resolved and unavailable members for the batch.

        Returns
        -------
        ObservedSession or None
            Persisted idle activity for s2, otherwise an unavailable result.
        """
        calls.append(session_id)
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(LazyActivity, "read", read)
    try:
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["s1", "s1", "s2", "missing"]}),
                headers={"content-type": "application/json"},
            )
    finally:
        await store.close()

    assert response.status_code == 200, "The batch endpoint must be mounted."
    assert response.headers.get("content-type", "").startswith(
        "application/x-ndjson"
    ), "Batch results must use NDJSON framing."
    assert response.headers.get("x-accel-buffering") == "no", (
        "Proxy buffering must be disabled so completed lookups can stream."
    )
    frames = [json.loads(line) for line in response.content.splitlines()]
    assert frames[0]["sessionId"] == "s1", (
        "Cached results must be streamed before fresh observer lookups."
    )
    assert {frame["sessionId"] for frame in frames} == {"missing", "s1", "s2"}, (
        "Input duplicates must collapse while every unique identifier gets a frame."
    )
    assert all(frame["workspaceId"] == "w1" for frame in frames), (
        "Each frame must carry the store's workspace identity."
    )
    by_session = {frame["sessionId"]: frame["session"] for frame in frames}
    assert by_session["s1"]["state"] == "idle", (
        "A valid cached projection must be returned as a successful frame."
    )
    assert by_session["s2"] is None, (
        "Unavailable reads and missing identities must produce null projections."
    )
    assert by_session["missing"] is None, (
        "Unavailable reads and missing identities must produce null projections."
    )
    assert calls == ["s2"], "Cache hits and missing sessions must skip Lody."


@pytest.mark.asyncio
async def test_duplicate_cached_ids_keep_their_first_request_order(
    tmp_path: Path,
) -> None:
    """Cached duplicate inputs produce one frame in first-occurrence order."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'ordered.sqlite3'}", "w1")
    await store.initialize()
    await _seed_unknown_sessions(store, ["s1", "s2"])
    await _remember_idle_activity(store, "s1")
    await _remember_idle_activity(store, "s2")
    try:
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["s2", "s1", "s2"]}),
                headers={"content-type": "application/json"},
            )
    finally:
        await store.close()

    frames = [json.loads(line) for line in response.content.splitlines()]
    assert [frame["sessionId"] for frame in frames] == ["s2", "s1"], (
        "Deduplication must preserve the first occurrence of each ID."
    )


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"{}",
        b'{"sessionIds":"s1"}',
        b'{"sessionIds":[1]}',
        json.dumps({"sessionIds": [f"s{index}" for index in range(9)]}).encode(),
        b'{"sessionIds":[""]}',
        json.dumps({"sessionIds": ["s" * 257]}).encode(),
        b'{"sessionIds":["s\\u0000x"]}',
    ],
)
@pytest.mark.asyncio
async def test_batch_rejects_invalid_request_shapes_and_ids(
    tmp_path: Path, body: bytes
) -> None:
    """Malformed JSON, too many IDs and unsafe identifiers return HTTP 400."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'invalid.sqlite3'}", "w1")
    await store.initialize()
    try:
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=body,
                headers={"content-type": "application/json"},
            )
    finally:
        await store.close()
    assert response.status_code == 400, (
        "Invalid activity batch input must be rejected before observation."
    )


@pytest.mark.asyncio
async def test_batch_rejects_a_body_over_8192_bytes(tmp_path: Path) -> None:
    """The request body limit is enforced before JSON decoding."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'oversized.sqlite3'}", "w1")
    await store.initialize()
    try:
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=b" " * 8_193,
                headers={"content-type": "application/json"},
            )
    finally:
        await store.close()
    assert response.status_code == 413, (
        "Oversized activity batches must fail with HTTP 413."
    )


@pytest.mark.asyncio
async def test_closing_stream_cancels_owned_lookup_waiters(tmp_path: Path) -> None:
    """Disconnecting after a cached frame reaps pending request waiters."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'cancel.sqlite3'}", "w1")
    await store.initialize()
    await _seed_unknown_sessions(store, ["s1", "s2"])
    await _remember_idle_activity(store, "s1")
    activity = _BlockingActivity()
    stream = BatchSessionActivityResource(store, activity)._stream_results(["s1", "s2"])
    try:
        first_frame = json.loads(await anext(stream))
        assert first_frame["sessionId"] == "s1", (
            "The cached frame must be available before waiting for the cold lookup."
        )
        await asyncio.wait_for(activity.started.wait(), timeout=1)
    finally:
        await stream.aclose()
        await store.close()
    assert activity.cancelled.is_set(), (
        "Closing the response stream must cancel its outstanding waiter task."
    )
