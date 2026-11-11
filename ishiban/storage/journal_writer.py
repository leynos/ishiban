"""Append validated events and attach immutable post-event projections."""

import dataclasses as dc
import typing as typ

from ishiban.storage.models import source_events
from ishiban.storage.serialization import encode_json

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from ishiban.domain import Envelope


@dc.dataclass(frozen=True, slots=True)
class ValidatedEnvelope:
    """Pair a typed event with its original validated source bytes."""

    envelope: Envelope
    raw_payload: bytes | None = None


@dc.dataclass(frozen=True, slots=True)
class JournalEvent:
    """Collect the source fields needed for one append-only event row."""

    source: str
    event_type: str
    payload: object
    received_at: str
    raw_payload: bytes | None = None
    stream_id: str | None = None
    sequence: int | None = None
    session_id: str | None = None
    observed_at: int | None = None


async def insert_event(
    connection: AsyncConnection, workspace_id: str, event: JournalEvent
) -> int:
    """Insert one journal event and return its durable local cursor.

    Returns
    -------
    int
        The autoincremented ``source_events.id`` cursor.
    """
    result = await connection.execute(
        source_events.insert().values(
            workspace_id=workspace_id,
            stream_id=event.stream_id,
            sequence=event.sequence,
            source=event.source,
            event_type=event.event_type,
            session_id=event.session_id,
            observed_at=event.observed_at,
            received_at=event.received_at,
            payload_json=(
                event.raw_payload.decode("utf-8")
                if event.raw_payload is not None
                else encode_json(event.payload)
            ),
            projection_json=None,
        )
    )
    return int(result.inserted_primary_key[0])


async def finish_event(
    connection: AsyncConnection,
    event_id: int,
    projection: dict[str, object],
) -> None:
    """Store the exact resulting public projection on the journal row."""
    await connection.execute(
        source_events
        .update()
        .where(source_events.c.id == event_id)
        .values(projection_json=encode_json(projection))
    )
