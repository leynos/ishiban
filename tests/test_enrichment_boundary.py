"""Retained-data queries never start children or change retained state."""

import dataclasses as dc
import sqlite3
import typing as typ

import msgspec
import pytest_asyncio
from batch_activity_support import remember_idle_activity, seed_unknown_sessions
from falcon import testing
from storage_support import opened_store

from ishiban.api import EventsResource, create_app

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox, SpyCommand

    from ishiban.storage import Store

CACHED_ID = "cached-session"
UNCACHED_ID = "uncached-session"
JOURNAL_NAME = "ishiban.sqlite3"
SIDE_CAR_SUFFIX = ".activity.sqlite3"
MAX_REPLAY_FRAMES = 8
SEEDED_SESSION_COUNT = 2
UNEXPECTED_EXIT = 1


@dc.dataclass(frozen=True, slots=True)
class RetainedState:
    """Committed state that retained-data queries must leave untouched."""

    events: list[dict[str, object]]
    cursor: int
    sidecar_rows: tuple[tuple[object, ...], ...]


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


def _sidecar_rows(directory: pathlib.Path) -> tuple[tuple[object, ...], ...]:
    """Return every retained activity row for the ``w1`` workspace.

    Comparing whole rows, rather than only their count, detects an in-place
    update or upsert of an existing cached session.

    Returns
    -------
    tuple of tuple of object
        Sidecar rows ordered by session identity.
    """
    sidecar = directory / f"{JOURNAL_NAME}{SIDE_CAR_SUFFIX}"
    with sqlite3.connect(sidecar) as connection:
        rows = connection.execute(
            "SELECT workspace_id, session_id, base_revision, runtime_json,"
            " saved_at_ns FROM activity_runtime_cache"
            " WHERE workspace_id = ? ORDER BY session_id",
            ("w1",),
        ).fetchall()
    return tuple(tuple(row) for row in rows)


async def _retained_state(store: Store, directory: pathlib.Path) -> RetainedState:
    """Capture the journal and sidecar facts a query must not change.

    Returns
    -------
    RetainedState
        Committed events, the durable cursor and the sidecar contents.
    """
    return RetainedState(
        events=await store.events(0),
        cursor=await store.current_cursor(),
        sidecar_rows=_sidecar_rows(directory),
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


async def _replayed_sessions(store: Store, cursor: int) -> dict[str, dict[str, object]]:
    """Collect the seeded projections from one bounded replay batch.

    Returns
    -------
    dict of str to dict of str to object
        Replayed projections keyed by their seeded session identity.
    """
    stream = EventsResource(store).tail(cursor)
    found: dict[str, dict[str, object]] = {}
    try:
        for _ in range(MAX_REPLAY_FRAMES):
            event = await anext(stream)
            frame = msgspec.convert(event.json, type=dict[str, object])
            raw = frame.get("projection")
            if not isinstance(raw, dict):
                continue
            projection = msgspec.convert(raw, type=dict[str, object])
            session_id = projection.get("sessionId")
            if isinstance(session_id, str) and session_id in {CACHED_ID, UNCACHED_ID}:
                found[session_id] = projection
            if len(found) == SEEDED_SESSION_COUNT:
                break
    finally:
        await stream.aclose()
    return found


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
            # its cursor parsing and SSE encoding are exercised over HTTP. The
            # open-ended live stream is read through ``tail`` below because
            # Falcon's test client joins a whole response body.
            events=await conductor.simulate_get(f"/api/v1/events?after={ahead}"),
            replayed=await _replayed_sessions(store, baseline),
        )
        # Read before shutdown closes the store that owns the connections.
        after = await _retained_state(store, directory)
    return responses, after


@pytest_asyncio.fixture
async def boundary_case(tmp_path: pathlib.Path, cmd_mox: CmdMox) -> BoundaryCase:
    """Serve retained-data routes against one cached and one uncached session.

    Returns
    -------
    BoundaryCase
        Captured responses, retained state and uninvoked command spies.
    """
    lody = cmd_mox.spy("lody").returns(
        stderr="retained-data queries must not read Lody.", exit_code=UNEXPECTED_EXIT
    )
    gh = cmd_mox.spy("gh").returns(
        stderr="retained-data queries must not read GitHub.", exit_code=UNEXPECTED_EXIT
    )
    async with opened_store(tmp_path) as store:
        baseline = await store.current_cursor()
        await seed_unknown_sessions(store, [CACHED_ID, UNCACHED_ID])
        await remember_idle_activity(store, CACHED_ID)
        before = await _retained_state(store, tmp_path)
        responses, after = await _exercise_routes(store, baseline, tmp_path)
    return BoundaryCase(before, responses, after, lody, gh)


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
    cached = _snapshot_session(snapshot, CACHED_ID)
    uncached = _snapshot_session(snapshot, UNCACHED_ID)
    assert (cached["state"], cached["activitySource"]) == ("idle", "lazy"), (
        "The snapshot overlays the cached row and keeps its provenance."
    )
    assert uncached["state"] == "unknown", "No cache row invents activity evidence."
    assert uncached.get("activitySource") is None, (
        "An uncached snapshot entry reports no lazy provenance."
    )

    path_session = _detail_session(
        msgspec.convert(responses.path_detail.json, type=dict[str, object])
    )
    assert (path_session["state"], path_session["activitySource"]) == (
        "idle",
        "lazy",
    ), "Path detail restores the cached row and keeps its provenance."

    query_session = _detail_session(
        msgspec.convert(responses.query_detail.json, type=dict[str, object])
    )
    assert query_session["state"] == "unknown", (
        "Query detail leaves an uncached session unknown."
    )
    assert query_session.get("activitySource") is None, (
        "Query detail reports no lazy provenance for an uncached session."
    )

    assert set(responses.replayed) == {CACHED_ID, UNCACHED_ID}, (
        "Replay exposes both seeded identities."
    )
    replayed_cached = responses.replayed[CACHED_ID]
    assert (replayed_cached["state"], replayed_cached["activitySource"]) == (
        "idle",
        "lazy",
    ), "Replay overlays the cached row on its committed event."
    assert responses.replayed[UNCACHED_ID]["state"] == "unknown", (
        "Replay does not invent evidence for an uncached session."
    )

    assert not boundary_case.lody.invocations, (
        "No retained-data query starts a Lody child."
    )
    assert not boundary_case.gh.invocations, (
        "No retained-data query starts a GitHub child."
    )
    assert boundary_case.after.events == boundary_case.before.events, (
        "Retained-data queries append no event."
    )
    assert boundary_case.after.cursor == boundary_case.before.cursor, (
        "Retained-data queries advance no cursor."
    )
    assert boundary_case.after.sidecar_rows == boundary_case.before.sidecar_rows, (
        "Retained-data queries change no retained activity field."
    )
