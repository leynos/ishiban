"""Bounded NDJSON activity batches resolve visible sessions independently."""

import asyncio
import json
import typing as typ

import pytest
from batch_activity_support import remember_idle_activity, seed_unknown_sessions
from falcon import testing
from storage_support import opened_store

from ishiban import domain, lazy_activity
from ishiban.api import create_app
from ishiban.batch_activity_api import BatchSessionActivityResource

if typ.TYPE_CHECKING:
    import pathlib


class _BlockingActivity(lazy_activity.LazyActivity):
    """Expose cancellation of a waiter owned by the batch response stream."""

    def __init__(self) -> None:
        """Create request-waiter lifecycle signals for the streaming test."""
        super().__init__("w1", "w1")
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self._release = asyncio.Event()

    async def read(
        self, session_id: str, revision: int
    ) -> domain.ObservedSession | None:
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
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cached, fresh, unavailable and missing members coexist in one batch."""
    calls: list[str] = []

    async def read(
        _activity: lazy_activity.LazyActivity, session_id: str, _revision: int
    ) -> domain.ObservedSession | None:
        """Return s2's fresh result and leave all other reads unavailable.

        Returns
        -------
        ObservedSession or None
            A persisted running session for s2, otherwise ``None``.
        """
        calls.append(session_id)
        await asyncio.sleep(0)
        if session_id == "s2":
            return domain.ObservedSession(
                session_id="s2",
                machine_id="machine-1",
                title="Fresh session s2",
                state="running",
                source="persisted",
                freshness="synced",
                latest_turn=domain.Turn("turn-s2", "running"),
            )
        return None

    monkeypatch.setattr(lazy_activity.LazyActivity, "read", read)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1", "s2", "s3"])
        await remember_idle_activity(store, "s1")
        baseline = await store.snapshot()
        journal_before = await store.events(0)
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["s1", "s1", "s2", "s3", "missing"]}),
                headers={"content-type": "application/json"},
            )
            snapshot_after = await store.snapshot()
            journal_after = await store.events(0)

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
    assert {frame["sessionId"] for frame in frames} == {
        "missing",
        "s1",
        "s2",
        "s3",
    }, "Input duplicates must collapse while every unique identifier gets a frame."
    assert all(frame["workspaceId"] == "w1" for frame in frames), (
        "Each frame must carry the store's workspace identity."
    )
    by_session = {frame["sessionId"]: frame["session"] for frame in frames}
    assert by_session["s1"]["state"] == "idle", (
        "A valid cached projection must be returned as a successful frame."
    )
    assert by_session["s1"]["activitySource"] == "lazy", (
        "Cached activity must retain its lazy provenance."
    )
    assert by_session["s2"]["state"] == "running", (
        "Fresh Lody evidence must be returned for a successful batch member."
    )
    assert by_session["s2"]["activitySource"] == "lazy", (
        "Fresh activity must be labelled as lazy evidence."
    )
    assert by_session["s3"] is None, "An unavailable member must not abort the batch."
    assert by_session["missing"] is None, "A missing member must yield a null frame."
    assert set(calls) == {"s2", "s3"}, "Cache hits and missing sessions must skip Lody."
    assert snapshot_after == baseline, "Batch enrichment must not change journal state."
    assert journal_after == journal_before, "Batch enrichment must not append events."


@pytest.mark.asyncio
async def test_duplicate_cached_ids_keep_their_first_request_order(
    tmp_path: pathlib.Path,
) -> None:
    """Cached duplicate inputs produce one frame in first-occurrence order."""
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1", "s2"])
        await remember_idle_activity(store, "s1")
        await remember_idle_activity(store, "s2")
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["s2", "s1", "s2"]}),
                headers={"content-type": "application/json"},
            )

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
    tmp_path: pathlib.Path, body: bytes
) -> None:
    """Malformed JSON, too many IDs and unsafe identifiers return HTTP 400."""
    async with (
        opened_store(tmp_path) as store,
        testing.ASGIConductor(create_app(store)) as conductor,
    ):
        response = await conductor.simulate_post(
            "/api/v1/sessions/activity",
            body=body,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 400, (
        "Invalid activity batch input must be rejected before observation."
    )


@pytest.mark.asyncio
async def test_batch_rejects_a_body_over_8192_bytes(tmp_path: pathlib.Path) -> None:
    """The request body limit is enforced before JSON decoding."""
    async with (
        opened_store(tmp_path) as store,
        testing.ASGIConductor(create_app(store)) as conductor,
    ):
        response = await conductor.simulate_post(
            "/api/v1/sessions/activity",
            body=b" " * 8_193,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413, (
        "Oversized activity batches must fail with HTTP 413."
    )


@pytest.mark.asyncio
async def test_closing_stream_cancels_owned_lookup_waiters(
    tmp_path: pathlib.Path,
) -> None:
    """Disconnecting after a cached frame reaps pending request waiters."""
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1", "s2"])
        await remember_idle_activity(store, "s1")
        activity = _BlockingActivity()
        stream = BatchSessionActivityResource(store, activity)._stream_results([
            "s1",
            "s2",
        ])
        try:
            first_frame = json.loads(await anext(stream))
            assert first_frame["sessionId"] == "s1", (
                "The cached frame must be available before waiting for the cold lookup."
            )
            await asyncio.wait_for(activity.started.wait(), timeout=1)
        finally:
            await stream.aclose()
    assert activity.cancelled.is_set(), (
        "Closing the response stream must cancel its outstanding waiter task."
    )
