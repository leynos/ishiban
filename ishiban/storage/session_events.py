"""Project and journal session-specific observer events atomically."""

import typing as typ

from ishiban.storage.journal_writer import (
    JournalEvent,
    ValidatedEnvelope,
    finish_event,
    insert_event,
)
from ishiban.storage.models import collector_state
from ishiban.storage.projection_writer import (
    load_session_projection,
    save_session_projection,
    save_turn_projections,
)
from ishiban.storage.projections import (
    SessionProjection,
    apply_observation,
    apply_removal,
    apply_turn_event,
)
from ishiban.storage.serialization import string_field, utc_timestamp

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


async def write_observation(
    connection: AsyncConnection,
    workspace_id: str,
    incoming: ValidatedEnvelope,
    generation: int,
) -> int:
    """Apply a persisted or metadata session observation.

    Returns
    -------
    int
        The cursor containing the resulting session projection.

    Raises
    ------
    ValueError
        If the event does not include a matching session projection.
    """
    envelope = incoming.envelope
    observed = envelope.session
    if observed is None:
        raise ValueError
    if envelope.session_id not in {None, observed.session_id}:
        raise ValueError
    previous = await load_session_projection(
        connection, workspace_id, observed.session_id
    )
    projection = apply_observation(previous, observed, generation, envelope.observed_at)
    return await _commit_session_event(connection, workspace_id, incoming, projection)


async def write_removal(
    connection: AsyncConnection, workspace_id: str, incoming: ValidatedEnvelope
) -> int:
    """Tombstone one session while retaining its existing turns.

    Returns
    -------
    int
        The cursor containing the tombstone projection.

    Raises
    ------
    ValueError
        If the event has no session identifier.
    """
    envelope = incoming.envelope
    if envelope.session_id is None:
        raise ValueError
    previous = await load_session_projection(
        connection, workspace_id, envelope.session_id
    )
    projection = apply_removal(previous, envelope.session_id)
    return await _commit_session_event(connection, workspace_id, incoming, projection)


async def write_turn(
    connection: AsyncConnection,
    workspace_id: str,
    incoming: ValidatedEnvelope,
    generation: int,
) -> int:
    """Apply a named turn transition without requiring its counterpart.

    Returns
    -------
    int
        The cursor containing the resulting session projection.

    Raises
    ------
    ValueError
        If the event lacks its session or stable user-turn identifier.
    """
    envelope = incoming.envelope
    if envelope.session_id is None or envelope.user_turn_id is None:
        raise ValueError
    previous = await load_session_projection(
        connection, workspace_id, envelope.session_id
    )
    projection = apply_turn_event(previous, envelope, generation)
    return await _commit_session_event(connection, workspace_id, incoming, projection)


async def _commit_session_event(
    connection: AsyncConnection,
    workspace_id: str,
    incoming: ValidatedEnvelope,
    projection: SessionProjection,
) -> int:
    """Commit a session projection and its source event together.

    Returns
    -------
    int
        The local cursor for the source event.
    """
    envelope = incoming.envelope
    received_at = utc_timestamp()
    session_id = string_field(projection, "sessionId")
    event_id = await insert_event(
        connection,
        workspace_id,
        JournalEvent(
            source="lody.observe",
            event_type=envelope.type,
            stream_id=envelope.stream_id,
            sequence=envelope.sequence,
            session_id=session_id,
            observed_at=envelope.observed_at,
            payload=envelope,
            received_at=received_at,
            raw_payload=incoming.raw_payload,
        ),
    )
    projection["lastEventId"] = event_id
    await save_session_projection(connection, workspace_id, projection)
    await save_turn_projections(connection, workspace_id, projection, event_id)
    await finish_event(connection, event_id, projection)
    await connection.execute(
        collector_state
        .update()
        .where(collector_state.c.workspace_id == workspace_id)
        .values(last_received_at=received_at, last_event_id=event_id)
    )
    return event_id
