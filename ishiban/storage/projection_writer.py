"""SQL helpers for session and stable turn projection rows."""

import typing as typ

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ishiban.storage.models import sessions, turns
from ishiban.storage.serialization import (
    decode_object,
    encode_json,
    optional_string_field,
    string_field,
)

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from ishiban.storage.projections import SessionProjection


async def load_session_projection(
    connection: AsyncConnection, workspace_id: str, session_id: str
) -> SessionProjection | None:
    """Load one session projection within the current write transaction.

    Returns
    -------
    dict[str, object] or None
        The current materialized projection, if one exists.
    """
    value = await connection.scalar(
        sa.select(sessions.c.projection_json).where(
            sessions.c.workspace_id == workspace_id,
            sessions.c.session_id == session_id,
        )
    )
    return decode_object(value) if value is not None else None


async def save_session_projection(
    connection: AsyncConnection,
    workspace_id: str,
    projection: SessionProjection,
) -> None:
    """Upsert a session projection while retaining identity columns.

    Parameters
    ----------
    connection : AsyncConnection
        The caller's active write transaction.
    workspace_id : str
        The workspace that owns the session.
    projection : SessionProjection
        The post-event public projection to persist.
    """
    session_id = string_field(projection, "sessionId")
    machine_id = string_field(projection, "machineId")
    statement = sqlite_insert(sessions).values(
        workspace_id=workspace_id,
        session_id=session_id,
        machine_id=machine_id,
        projection_json=encode_json(projection),
    )
    await connection.execute(
        statement.on_conflict_do_update(
            index_elements=["workspace_id", "session_id"],
            set_={"machine_id": machine_id, "projection_json": encode_json(projection)},
        )
    )


async def save_turn_projections(
    connection: AsyncConnection,
    workspace_id: str,
    projection: SessionProjection,
    event_id: int,
) -> None:
    """Upsert latest-known turns without deleting historical user-turn IDs.

    Parameters
    ----------
    connection : AsyncConnection
        The caller's active write transaction.
    workspace_id : str
        The workspace that owns the session.
    projection : SessionProjection
        The post-event projection containing the current turn fields.
    event_id : int
        The local journal cursor for the transition.
    """
    known_turns: list[dict[str, object]] = []
    latest = projection.get("latestTurn")
    if isinstance(latest, dict):
        known_turns.append(typ.cast("dict[str, object]", latest))
    active = projection.get("activeTurns")
    if isinstance(active, list):
        known_turns.extend(
            typ.cast("dict[str, object]", turn)
            for turn in active
            if isinstance(turn, dict)
        )

    for turn in known_turns:
        user_turn_id = string_field(turn, "userTurnId")
        assistant_turn_id = optional_string_field(turn, "assistantTurnId")
        state = string_field(turn, "state")
        duration_ms = _optional_int(turn, "durationMs")
        turn_json = encode_json(turn)
        statement = sqlite_insert(turns).values(
            workspace_id=workspace_id,
            session_id=string_field(projection, "sessionId"),
            user_turn_id=user_turn_id,
            assistant_turn_id=assistant_turn_id,
            state=state,
            duration_ms=duration_ms,
            last_event_id=event_id,
            projection_json=turn_json,
        )
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=["workspace_id", "session_id", "user_turn_id"],
                set_={
                    "assistant_turn_id": assistant_turn_id,
                    "state": state,
                    "duration_ms": duration_ms,
                    "last_event_id": event_id,
                    "projection_json": turn_json,
                },
            )
        )


def _optional_int(projection: dict[str, object], key: str) -> int | None:
    """Read an optional integer field from a JSON projection.

    Returns
    -------
    int or None
        The integer value, or ``None`` when it is absent or non-integer.
    """
    value = projection.get(key)
    return value if isinstance(value, int) else None
