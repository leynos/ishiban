"""Consistent read queries for snapshots, detail and event replay."""

import typing as typ

import sqlalchemy as sa

from ishiban.detail_pagination import TURN_PAGE_SIZE, TurnPageCursor, encode_turn_cursor
from ishiban.storage.models import collector_state, sessions, source_events, turns
from ishiban.storage.projection_writer import load_session_projection
from ishiban.storage.serialization import decode_object

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


async def read_snapshot(
    connection: AsyncConnection, workspace_id: str
) -> dict[str, object]:
    """Read cursor, collector and all sessions within the caller's transaction.

    Returns
    -------
    dict[str, object]
        The contract snapshot assembled from one read transaction.
    """
    cursor = await read_cursor(connection, workspace_id)
    collector_row = (
        (
            await connection.execute(
                sa.select(collector_state).where(
                    collector_state.c.workspace_id == workspace_id
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    session_rows = (
        await connection.execute(
            sa
            .select(sessions.c.projection_json)
            .where(sessions.c.workspace_id == workspace_id)
            .order_by(sessions.c.session_id)
        )
    ).scalars()
    projection_rows = [decode_object(value) for value in session_rows]
    return {
        "version": 1,
        "workspaceId": workspace_id,
        "cursor": cursor,
        "collector": _collector_projection(collector_row),
        "sessions": projection_rows,
    }


async def read_cursor(connection: AsyncConnection, workspace_id: str) -> int:
    """Read only the maximum journal ID belonging to one workspace.

    Example
    -------
    cursor = await read_cursor(connection, "workspace-1")
    assert cursor >= 0  # An empty workspace has cursor zero.

    Returns
    -------
    int
        The workspace's latest local journal cursor, or zero before its first
        event.
    """
    cursor = await connection.scalar(
        sa.select(sa.func.coalesce(sa.func.max(source_events.c.id), 0)).where(
            source_events.c.workspace_id == workspace_id
        )
    )
    return int(cursor or 0)


async def read_detail(
    connection: AsyncConnection,
    workspace_id: str,
    session_id: str,
    after: TurnPageCursor | None = None,
) -> dict[str, object] | None:
    """Read one projection, a bounded turn page and recent provenance.

    For example, a continuation after ``u099`` starts with the next ordered
    turn, even when both turns have the same last event ID.

    Returns
    -------
    dict[str, object] or None
        The session detail record, or ``None`` when the session is unknown.
    """
    session_projection = await load_session_projection(
        connection, workspace_id, session_id
    )
    if session_projection is None:
        return None

    turn_page, next_cursor = await _read_turn_page(
        connection, workspace_id, session_id, after
    )
    recent_rows = (
        await connection.execute(
            sa
            .select(source_events)
            .where(
                source_events.c.workspace_id == workspace_id,
                source_events.c.session_id == session_id,
            )
            .order_by(source_events.c.id.desc())
            .limit(30)
        )
    ).mappings()
    return {
        "session": session_projection,
        "turns": turn_page,
        "nextTurnCursor": next_cursor,
        "recentEvents": [
            {
                "cursor": event.id,
                "source": event.source,
                "eventType": event.event_type,
                "observedAt": event.observed_at,
            }
            for event in recent_rows
        ],
    }


async def _read_turn_page(
    connection: AsyncConnection,
    workspace_id: str,
    session_id: str,
    after: TurnPageCursor | None,
) -> tuple[list[dict[str, object]], str | None]:
    """Read one keyset page and its continuation, bounded by lookahead.

    For example, 101 retained rows produce 100 turns and a continuation.

    Returns
    -------
    tuple[list[dict[str, object]], str | None]
        The decoded turn page and its optional next position.
    """
    turn_query = (
        sa
        .select(turns.c.projection_json, turns.c.last_event_id, turns.c.user_turn_id)
        .where(
            turns.c.workspace_id == workspace_id,
            turns.c.session_id == session_id,
        )
        .order_by(turns.c.last_event_id, turns.c.user_turn_id)
        .limit(TURN_PAGE_SIZE + 1)
    )
    if after is not None:
        turn_query = turn_query.where(
            sa.tuple_(turns.c.last_event_id, turns.c.user_turn_id)
            > (after.last_event_id, after.user_turn_id)
        )
    turn_rows = (await connection.execute(turn_query)).all()
    page = turn_rows[:TURN_PAGE_SIZE]
    next_cursor = None
    if len(turn_rows) > TURN_PAGE_SIZE:
        last = page[-1]
        next_cursor = encode_turn_cursor(
            TurnPageCursor(
                1, workspace_id, session_id, last.last_event_id, last.user_turn_id
            )
        )
    return (
        [
            {
                **decode_object(turn.projection_json),
                "lastEventId": turn.last_event_id,
            }
            for turn in page
        ],
        next_cursor,
    )


async def read_events(
    connection: AsyncConnection,
    workspace_id: str,
    after: int,
    limit: int,
) -> list[dict[str, object]]:
    """Read a bounded, ordered batch of committed source events.

    Returns
    -------
    list[dict[str, object]]
        The SSE payloads ordered by their local cursors.
    """
    rows = (
        await connection.execute(
            sa
            .select(source_events)
            .where(
                source_events.c.workspace_id == workspace_id,
                source_events.c.id > after,
            )
            .order_by(source_events.c.id)
            .limit(limit)
        )
    ).mappings()
    events: list[dict[str, object]] = []
    for row in rows:
        event: dict[str, object] = {
            "cursor": row["id"],
            "workspaceId": workspace_id,
            "source": row["source"],
            "eventType": row["event_type"],
            "projection": decode_object(row["projection_json"]),
        }
        if row["session_id"] is not None:
            event["sessionId"] = row["session_id"]
        events.append(event)
    return events


def _collector_projection(row: sa.RowMapping | None) -> dict[str, object]:
    """Normalize persisted or initial collector health to the public contract.

    Returns
    -------
    dict[str, object]
        The required collector fields in the public camel-case shape.
    """
    if row is None:
        return {
            "state": "stopped",
            "generation": 0,
            "lastError": None,
            "lastReceivedAt": None,
        }
    return {
        "state": row["state"],
        "generation": row["generation"],
        "lastError": row["last_error"],
        "lastReceivedAt": row["last_received_at"],
    }
