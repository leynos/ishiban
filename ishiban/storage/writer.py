"""Serialize and dispatch atomic journal writes for one workspace."""

import typing as typ

import sqlalchemy as sa

from ishiban.storage.journal_writer import (
    JournalEvent,
    ValidatedEnvelope,
    finish_event,
    insert_event,
)
from ishiban.storage.models import collector_state, source_events
from ishiban.storage.projection_writer import (
    load_session_projection,
    save_session_projection,
)
from ishiban.storage.projections import apply_catalogue
from ishiban.storage.serialization import utc_timestamp
from ishiban.storage.session_events import write_observation, write_removal, write_turn

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from ishiban.domain import CatalogueEntry, Envelope


class JournalWriter:
    """Write source rows and their post-event projections transactionally."""

    def __init__(self, workspace_id: str) -> None:
        """Bind journal writes to one configured workspace."""
        self.workspace_id = workspace_id

    async def begin_generation(self, connection: AsyncConnection) -> int:
        """Persist a connecting health event and return the new generation.

        Returns
        -------
        int
            The new local collector generation.
        """
        current = await self._collector_row(connection)
        generation = int(current["generation"]) + 1
        event_id = await insert_event(
            connection,
            self.workspace_id,
            JournalEvent(
                source="collector",
                event_type="generation.started",
                payload={"generation": generation},
                received_at=utc_timestamp(),
            ),
        )
        projection = {
            "state": "connecting",
            "generation": generation,
            "lastError": None,
            "lastReceivedAt": current["last_received_at"],
        }
        await connection.execute(
            collector_state
            .update()
            .where(collector_state.c.workspace_id == self.workspace_id)
            .values(
                generation=generation,
                state="connecting",
                last_error=None,
                last_event_id=event_id,
            )
        )
        await finish_event(connection, event_id, projection)
        return generation

    async def health(
        self,
        connection: AsyncConnection,
        state: str,
        generation: int,
        error: str | None,
    ) -> int:
        """Persist collector health without changing session evidence.

        Returns
        -------
        int
            The local cursor for the health change.
        """
        current = await self._collector_row(connection)
        self._require_generation(current, generation)
        bounded_error = error[:500] if error is not None else None
        event_id = await insert_event(
            connection,
            self.workspace_id,
            JournalEvent(
                source="collector",
                event_type="health.changed",
                payload={
                    "state": state,
                    "generation": generation,
                    "error": bounded_error,
                },
                received_at=utc_timestamp(),
            ),
        )
        projection = {
            "state": state,
            "generation": generation,
            "lastError": bounded_error,
            "lastReceivedAt": current["last_received_at"],
        }
        await connection.execute(
            collector_state
            .update()
            .where(collector_state.c.workspace_id == self.workspace_id)
            .values(state=state, last_error=bounded_error, last_event_id=event_id)
        )
        await finish_event(connection, event_id, projection)
        return event_id

    async def ingest(
        self,
        connection: AsyncConnection,
        incoming: ValidatedEnvelope,
        generation: int,
    ) -> int:
        """Deduplicate, journal and project one validated observer event.

        Returns
        -------
        int
            The original or newly committed local cursor.

        Raises
        ------
        ValueError
            If the event version or event type is unsupported.
        """
        envelope = incoming.envelope
        duplicate = await self._duplicate_cursor(connection, envelope)
        if duplicate is not None:
            return duplicate
        current = await self._collector_row(connection)
        self._require_generation(current, generation)
        if envelope.version != 1:
            raise ValueError

        return await self._write_event(connection, incoming, current, generation)

    async def _write_event(
        self,
        connection: AsyncConnection,
        incoming: ValidatedEnvelope,
        current: sa.RowMapping,
        generation: int,
    ) -> int:
        """Route a validated, nonduplicate event to its projection writer.

        For example, turn transitions use the same generation-aware writer.

        Returns
        -------
        int
            The new journal cursor assigned by the selected writer.

        Raises
        ------
        ValueError
            If no writer supports this event type.
        """
        envelope = incoming.envelope
        if envelope.type in {"ready", "error"}:
            return await self._ingest_collector_event(
                connection, incoming, current, generation
            )
        if envelope.type in {"snapshot", "session.changed"}:
            return await write_observation(
                connection, self.workspace_id, incoming, generation
            )
        if envelope.type == "session.removed":
            return await write_removal(connection, self.workspace_id, incoming)
        if envelope.type in {"turn.started", "turn.finished"}:
            return await write_turn(connection, self.workspace_id, incoming, generation)
        raise ValueError

    async def catalogue(
        self,
        connection: AsyncConnection,
        entry: CatalogueEntry,
        generation: int,
    ) -> int | None:
        """Persist catalogue enrichment only when its projection changes.

        Returns
        -------
        int or None
            The local cursor, or ``None`` when no public field changed.
        """
        current = await self._collector_row(connection)
        self._require_generation(current, generation)
        previous = await load_session_projection(
            connection, self.workspace_id, entry.session_id
        )
        projection = apply_catalogue(previous, entry, generation)
        if previous == projection:
            return None

        event_id = await insert_event(
            connection,
            self.workspace_id,
            JournalEvent(
                source="lody.catalogue",
                event_type="catalogue.changed",
                session_id=entry.session_id,
                payload=entry,
                received_at=utc_timestamp(),
            ),
        )
        projection["lastEventId"] = event_id
        await save_session_projection(connection, self.workspace_id, projection)
        await finish_event(connection, event_id, projection)
        await connection.execute(
            collector_state
            .update()
            .where(collector_state.c.workspace_id == self.workspace_id)
            .values(last_event_id=event_id)
        )
        return event_id

    async def _ingest_collector_event(
        self,
        connection: AsyncConnection,
        incoming: ValidatedEnvelope,
        current: sa.RowMapping,
        generation: int,
    ) -> int:
        """Record source readiness or failure as a collector projection.

        Returns
        -------
        int
            The local cursor for the collector state change.
        """
        envelope = incoming.envelope
        state = "catalogue_ready" if envelope.type == "ready" else "error"
        received_at = utc_timestamp()
        event_id = await insert_event(
            connection,
            self.workspace_id,
            JournalEvent(
                source="collector",
                event_type=envelope.type,
                stream_id=envelope.stream_id,
                sequence=envelope.sequence,
                observed_at=envelope.observed_at,
                payload=envelope,
                received_at=received_at,
                raw_payload=incoming.raw_payload,
            ),
        )
        projection = {
            "state": state,
            "generation": generation,
            "lastError": current["last_error"],
            "lastReceivedAt": received_at,
        }
        await connection.execute(
            collector_state
            .update()
            .where(collector_state.c.workspace_id == self.workspace_id)
            .values(state=state, last_received_at=received_at, last_event_id=event_id)
        )
        await finish_event(connection, event_id, projection)
        return event_id

    async def _duplicate_cursor(
        self, connection: AsyncConnection, envelope: Envelope
    ) -> int | None:
        """Return the original durable cursor for a repeated stream identity.

        Returns
        -------
        int or None
            The existing cursor, if the stream event was already committed.
        """
        value = await connection.scalar(
            sa.select(source_events.c.id).where(
                source_events.c.workspace_id == self.workspace_id,
                source_events.c.stream_id == envelope.stream_id,
                source_events.c.sequence == envelope.sequence,
            )
        )
        return int(value) if value is not None else None

    async def _collector_row(self, connection: AsyncConnection) -> sa.RowMapping:
        """Load collector state or fail when initialization was skipped.

        Returns
        -------
        sqlalchemy.engine.RowMapping
            The configured workspace's collector state.

        Raises
        ------
        RuntimeError
            If initialization did not seed this workspace.
        """
        row = (
            (
                await connection.execute(
                    sa.select(collector_state).where(
                        collector_state.c.workspace_id == self.workspace_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise RuntimeError
        return row

    @staticmethod
    def _require_generation(current: sa.RowMapping, generation: int) -> None:
        """Reject writes from a superseded observer generation.

        Raises
        ------
        ValueError
            If the supplied generation is no longer current.
        """
        if int(current["generation"]) != generation:
            raise ValueError
