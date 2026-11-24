"""Shared fixtures and readers for the enrichment boundary regression tests."""

import asyncio
import contextlib as ctx
import dataclasses as dc
import sqlite3
import typing as typ

import msgspec
from falcon import testing

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
MAX_STREAM_SECONDS = 15.0
SEEDED_SESSION_COUNT = 2
UNEXPECTED_EXIT = 1
SEEDED_IDS = frozenset({CACHED_ID, UNCACHED_ID})


@dc.dataclass(frozen=True, slots=True)
class RetainedState:
    """Committed state that retained-data queries must leave untouched."""

    events: list[dict[str, object]]
    cursor: int
    sidecar_rows: tuple[tuple[object, ...], ...]


def sidecar_rows(
    directory: pathlib.Path, workspace_id: str
) -> tuple[tuple[object, ...], ...]:
    """Return every retained activity row for one workspace.

    Comparing whole rows, rather than only their count, detects an in-place
    update or upsert of an existing cached session.

    Returns
    -------
    tuple of tuple of object
        Sidecar rows ordered by session identity.
    """
    sidecar = directory / f"{JOURNAL_NAME}{SIDE_CAR_SUFFIX}"
    # sqlite3's connection context manager only commits or rolls back; closing
    # the handle as well avoids leaking it in the test process.
    with ctx.closing(sqlite3.connect(sidecar)) as connection:
        rows = connection.execute(
            "SELECT workspace_id, session_id, base_revision, runtime_json,"
            " saved_at_ns FROM activity_runtime_cache"
            " WHERE workspace_id = ? ORDER BY session_id",
            (workspace_id,),
        ).fetchall()
    return tuple(tuple(row) for row in rows)


async def retained_state(store: Store, directory: pathlib.Path) -> RetainedState:
    """Capture the journal and sidecar facts a query must not change.

    Returns
    -------
    RetainedState
        Committed events, the durable cursor and the sidecar contents.
    """
    return RetainedState(
        events=await store.events(0),
        cursor=await store.current_cursor(),
        sidecar_rows=sidecar_rows(directory, store.workspace_id),
    )


def failing_spy(cmd_mox: CmdMox, name: str) -> SpyCommand:
    """Register a failing stand-in for one child that a query must not start.

    Returns
    -------
    SpyCommand
        Spy whose non-zero exit makes an accidental invocation fail loudly.
    """
    return cmd_mox.spy(name).returns(
        stderr=f"retained-data queries must not run {name}.",
        exit_code=UNEXPECTED_EXIT,
    )


def session_projection(row: dict[str, object]) -> dict[str, object] | None:
    """Return one seeded session projection from a replay row, if present.

    Returns
    -------
    dict of str to object or None
        The projection for a seeded identity, or ``None`` for other rows.
    """
    raw = row.get("projection")
    if not isinstance(raw, dict):
        return None
    projection = msgspec.convert(raw, type=dict[str, object])
    session_id = projection.get("sessionId")
    if not isinstance(session_id, str) or session_id not in SEEDED_IDS:
        return None
    return projection


async def replay_sessions(store: Store, cursor: int) -> dict[str, dict[str, object]]:
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
            projection = session_projection(
                msgspec.convert(event.json, type=dict[str, object])
            )
            if projection is not None:
                found[str(projection["sessionId"])] = projection
            if len(found) == SEEDED_SESSION_COUNT:
                break
    finally:
        await stream.aclose()
    return found


def streamed_sessions(data: bytes) -> dict[str, dict[str, object]]:
    """Decode seeded projections from accumulated SSE bytes.

    Returns
    -------
    dict of str to dict of str to object
        Streamed projections keyed by their seeded session identity.
    """
    found: dict[str, dict[str, object]] = {}
    for block in data.decode("utf-8").split("\n\n"):
        payload = next(
            (
                line.removeprefix("data: ")
                for line in block.splitlines()
                if line.startswith("data: ")
            ),
            None,
        )
        if payload is None:
            continue
        row = msgspec.convert(msgspec.json.decode(payload), type=dict[str, object])
        projection = session_projection(row)
        if projection is not None:
            found[str(projection["sessionId"])] = projection
    return found


async def read_streamed_sessions(
    stream: testing.ResultBodyStream,
) -> dict[str, dict[str, object]]:
    """Read the live event stream until both seeded sessions arrive.

    Returns
    -------
    dict of str to dict of str to object
        Streamed projections keyed by their seeded session identity.
    """
    data = b""
    async with asyncio.timeout(MAX_STREAM_SECONDS):
        while True:
            found = streamed_sessions(data)
            if len(found) == SEEDED_SESSION_COUNT:
                return found
            chunk = await stream.read()
            if chunk:
                data += chunk
            else:
                await asyncio.sleep(0.02)


async def stream_replay(
    store: Store, directory: pathlib.Path
) -> tuple[dict[str, dict[str, object]], RetainedState]:
    """Stream the normal events route over ASGI and close it after two frames.

    Returns
    -------
    tuple of dict and RetainedState
        Streamed projections and the state observed before ASGI shutdown.
    """
    async with testing.ASGIConductor(create_app(store)) as conductor:
        async with conductor.simulate_get_stream("/api/v1/events?after=0") as streamed:
            frames = await read_streamed_sessions(streamed.stream)
        # Read before shutdown closes the store that owns the connections.
        after = await retained_state(store, directory)
    return frames, after
