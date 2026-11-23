"""Retained-data queries never start children or change retained state."""

import dataclasses as dc
import typing as typ

import msgspec
import pytest_asyncio
from batch_activity_support import remember_idle_activity, seed_unknown_sessions
from enrichment_boundary_support import (
    CACHED_ID,
    UNCACHED_ID,
    RetainedState,
    failing_spy,
    replay_sessions,
    retained_state,
    stream_replay,
)
from falcon import testing
from storage_support import opened_store

from ishiban import api
from ishiban.api import create_app

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from cmd_mox import CmdMox, SpyCommand

    from ishiban.storage import Store


@dc.dataclass(frozen=True, slots=True)
class RouteResponses:
    """Complete responses produced by one retained-data request sequence."""

    snapshot: testing.Result
    path_detail: testing.Result
    query_detail: testing.Result
    events: testing.Result
    replayed: dict[str, dict[str, object]]


@dc.dataclass(frozen=True, slots=True)
class BoundaryCase:
    """Retained state, route responses and the children those routes avoided."""

    before: RetainedState
    responses: RouteResponses
    after: RetainedState
    lody: SpyCommand
    gh: SpyCommand


@dc.dataclass(frozen=True, slots=True)
class StreamedCase:
    """Streamed HTTP replay frames and the retained state around them."""

    before: RetainedState
    frames: dict[str, dict[str, object]]
    after: RetainedState
    lody: SpyCommand
    gh: SpyCommand


def _assert_cached_activity(session: dict[str, object], source: str) -> None:
    """Assert one response keeps the cached row and its lazy provenance."""
    assert (session["state"], session["activitySource"]) == ("idle", "lazy"), (
        f"{source} must overlay the cached row and keep its provenance."
    )


def _assert_uncached_activity(session: dict[str, object], source: str) -> None:
    """Assert one response invents no activity for an uncached session."""
    assert session["state"] == "unknown", f"{source} must not invent activity evidence."
    assert session.get("activitySource") is None, (
        f"{source} must report no lazy provenance for an uncached session."
    )


def _snapshot_session(
    snapshot: dict[str, object], session_id: str
) -> dict[str, object]:
    """Return one snapshot entry by identity.

    Returns
    -------
    dict of str to object
        The public projection emitted for ``session_id``.
    """
    sessions = msgspec.convert(snapshot["sessions"], type=list[dict[str, object]])
    matches = [item for item in sessions if item.get("sessionId") == session_id]
    assert len(matches) == 1, "Each seeded identity appears in one snapshot entry."
    return matches[0]


def _detail_session(payload: dict[str, object]) -> dict[str, object]:
    """Return the session projection carried by one detail response.

    Returns
    -------
    dict of str to object
        The detail payload's session projection.
    """
    return msgspec.convert(payload["session"], type=dict[str, object])


async def _exercise_routes(
    store: Store, baseline: int, directory: pathlib.Path
) -> tuple[RouteResponses, RetainedState]:
    """Serve every retained-data route and capture the state it leaves behind.

    Returns
    -------
    tuple of RouteResponses and RetainedState
        The route responses and the state observed before ASGI shutdown.
    """
    async with testing.ASGIConductor(create_app(store)) as conductor:
        ahead = await store.current_cursor() + 1
        responses = RouteResponses(
            snapshot=await conductor.simulate_get("/api/v1/snapshot"),
            path_detail=await conductor.simulate_get(f"/api/v1/sessions/{CACHED_ID}"),
            query_detail=await conductor.simulate_get(
                f"/api/v1/session-detail?sessionId={UNCACHED_ID}"
            ),
            # A cursor ahead of retained order finishes at once, so the route,
            # its cursor parsing and SSE encoding are exercised here over HTTP.
            # The normal replay stream is covered separately by
            # ``test_events_route_streams_overlaid_replay_frames``.
            events=await conductor.simulate_get(f"/api/v1/events?after={ahead}"),
            replayed=await replay_sessions(store, baseline),
        )
        # Read before shutdown closes the store that owns the connections.
        after = await retained_state(store, directory)
    return responses, after


async def _seed_boundary_store(store: Store, directory: pathlib.Path) -> RetainedState:
    """Seed one cached and one uncached unknown session.

    Returns
    -------
    RetainedState
        The retained state after seeding and before any query.
    """
    await seed_unknown_sessions(store, [CACHED_ID, UNCACHED_ID])
    await remember_idle_activity(store, CACHED_ID)
    return await retained_state(store, directory)


@pytest_asyncio.fixture
async def boundary_case(tmp_path: pathlib.Path, cmd_mox: CmdMox) -> BoundaryCase:
    """Serve retained-data routes against one cached and one uncached session.

    Returns
    -------
    BoundaryCase
        Captured responses, retained state and uninvoked command spies.
    """
    lody = failing_spy(cmd_mox, "lody")
    gh = failing_spy(cmd_mox, "gh")
    async with opened_store(tmp_path) as store:
        baseline = await store.current_cursor()
        before = await _seed_boundary_store(store, tmp_path)
        responses, after = await _exercise_routes(store, baseline, tmp_path)
    return BoundaryCase(before, responses, after, lody, gh)


@pytest_asyncio.fixture
async def streamed_case(
    tmp_path: pathlib.Path,
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
) -> StreamedCase:
    """Stream the events route against one cached and one uncached session.

    Returns
    -------
    StreamedCase
        Streamed frames, surrounding retained state and uninvoked spies.
    """
    # Falcon notices a client disconnect only when the SSE generator yields.
    # A one-poll heartbeat keeps stream teardown bounded without changing what
    # the test asserts about replay.
    monkeypatch.setattr(api, "HEARTBEAT_POLLS", 1)
    lody = failing_spy(cmd_mox, "lody")
    gh = failing_spy(cmd_mox, "gh")
    async with opened_store(tmp_path) as store:
        before = await _seed_boundary_store(store, tmp_path)
        frames, after = await stream_replay(store, tmp_path)
    return StreamedCase(before, frames, after, lody, gh)


def _assert_no_upstream(spies: tuple[SpyCommand, SpyCommand], source: str) -> None:
    """Assert neither upstream command was invoked for this route class."""
    lody, gh = spies
    assert not lody.invocations, f"{source} must not start a Lody child."
    assert not gh.invocations, f"{source} must not start a GitHub child."


def _assert_retained_state_unchanged(
    before: RetainedState, after: RetainedState, source: str
) -> None:
    """Assert the journal, cursor and retained activity are untouched."""
    assert after.events == before.events, f"{source} must append no event."
    assert after.cursor == before.cursor, f"{source} must advance no cursor."
    assert after.sidecar_rows == before.sidecar_rows, (
        f"{source} must change no retained activity field."
    )


def test_retained_data_queries_use_only_retained_state(
    boundary_case: BoundaryCase,
) -> None:
    """Snapshot, detail and replay answer without an upstream child or write."""
    responses = boundary_case.responses
    assert (
        responses.snapshot.status_code,
        responses.path_detail.status_code,
        responses.query_detail.status_code,
        responses.events.status_code,
    ) == (200, 200, 200, 200), (
        "Every retained-data route must serve the committed journal."
    )
    assert '"reason": "cursor_ahead"' in responses.events.text, (
        "The events route rejects a cursor ahead of retained order."
    )

    snapshot = msgspec.convert(responses.snapshot.json, type=dict[str, object])
    _assert_cached_activity(_snapshot_session(snapshot, CACHED_ID), "The snapshot")
    _assert_uncached_activity(_snapshot_session(snapshot, UNCACHED_ID), "The snapshot")

    path_session = _detail_session(
        msgspec.convert(responses.path_detail.json, type=dict[str, object])
    )
    _assert_cached_activity(path_session, "Path detail")

    query_session = _detail_session(
        msgspec.convert(responses.query_detail.json, type=dict[str, object])
    )
    _assert_uncached_activity(query_session, "Query detail")

    assert set(responses.replayed) == {CACHED_ID, UNCACHED_ID}, (
        "Replay exposes both seeded identities."
    )
    _assert_cached_activity(responses.replayed[CACHED_ID], "Replay")
    _assert_uncached_activity(responses.replayed[UNCACHED_ID], "Replay")

    _assert_no_upstream((boundary_case.lody, boundary_case.gh), "Retained-data queries")
    _assert_retained_state_unchanged(
        boundary_case.before, boundary_case.after, "Retained-data queries"
    )


def test_events_route_streams_overlaid_replay_frames(
    streamed_case: StreamedCase,
) -> None:
    """The normal events stream overlays activity without an upstream child."""
    assert set(streamed_case.frames) == {CACHED_ID, UNCACHED_ID}, (
        "The streamed route exposes both seeded identities."
    )
    _assert_cached_activity(streamed_case.frames[CACHED_ID], "The streamed route")
    _assert_uncached_activity(streamed_case.frames[UNCACHED_ID], "The streamed route")

    _assert_no_upstream((streamed_case.lody, streamed_case.gh), "The streamed route")
    _assert_retained_state_unchanged(
        streamed_case.before, streamed_case.after, "The streamed route"
    )
