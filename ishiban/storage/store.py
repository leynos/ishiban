"""Public async API for the SQLite journal and materialized projections."""

import asyncio
import typing as typ

import sqlalchemy as sa

from ishiban.storage.database import create_engine, initialize_schema, verify_schema
from ishiban.storage.journal_writer import ValidatedEnvelope
from ishiban.storage.reader import read_cursor, read_detail, read_events, read_snapshot
from ishiban.storage.writer import JournalWriter

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from ishiban.domain import CatalogueEntry, Envelope


class Store:
    """Persist one workspace's observation journal and current projections.

    Example
    -------
    store = Store("sqlite+aiosqlite:///ishiban.db", "workspace-1")
    await store.initialize()
    snapshot = await store.snapshot()
    await store.close()
    """

    def __init__(self, database_url: str, workspace_id: str) -> None:
        """Create a workspace-bound store without opening a connection."""
        self.workspace_id = workspace_id
        self._engine: AsyncEngine = create_engine(database_url)
        self._writer = JournalWriter(workspace_id)
        self._write_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self, *, migrate: bool = True) -> None:
        """Open the store, optionally applying Alembic migrations.

        Example
        -------
        await store.initialize()
        assert (await store.snapshot())["cursor"] == 0

        A read-only API process verifies the existing head without upgrading:

        await api_store.initialize(migrate=False)

        """
        if self._initialized:
            return
        if migrate:
            await initialize_schema(self._engine)
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT OR IGNORE INTO collector_state "
                        "(workspace_id, generation, state, last_error, "
                        "last_received_at, last_event_id) "
                        "VALUES (:workspace_id, 0, 'stopped', NULL, NULL, 0)"
                    ),
                    {"workspace_id": self.workspace_id},
                )
        else:
            await verify_schema(self._engine)
        self._initialized = True

    async def close(self) -> None:
        """Dispose connections while leaving every committed row intact.

        Example
        -------
        await store.close()
        """
        await self._engine.dispose()
        self._initialized = False

    async def begin_generation(self) -> int:
        """Persist ``connecting`` health and return the next local generation.

        Example
        -------
        generation = await store.begin_generation()
        assert (await store.snapshot())["collector"]["generation"] == generation

        Returns
        -------
        int
            The persisted local collector generation.
        """
        self._require_initialized()
        async with self._write_lock, self._engine.begin() as connection:
            return await self._writer.begin_generation(connection)

    async def ingest(
        self,
        envelope: Envelope,
        generation: int,
        *,
        raw: bytes | None = None,
    ) -> int:
        """Commit one validated event and return its durable local cursor.

        Duplicate ``(streamId, sequence)`` pairs return their original cursor.
        Example
        -------
        cursor = await store.ingest(envelope, generation=1)
        assert (await store.events(after=cursor - 1))[0]["cursor"] == cursor

        Pass the validated source line as ``raw`` to preserve unknown v1 fields.

        Returns
        -------
        int
            The event's original or newly assigned local cursor.

        Raises
        ------
        ValueError
            If the event names a different workspace.
        """
        self._require_initialized()
        if envelope.workspace_id != self.workspace_id:
            raise ValueError
        async with self._write_lock, self._engine.begin() as connection:
            return await self._writer.ingest(
                connection, ValidatedEnvelope(envelope, raw), generation
            )

    async def catalogue(self, entry: CatalogueEntry, generation: int) -> int | None:
        """Commit changed catalogue metadata, or return ``None`` for no change.

        Example
        -------
        cursor = await store.catalogue(entry, generation=1)
        assert cursor is None or cursor > 0

        Returns
        -------
        int or None
            The new cursor, or ``None`` if no public field changed.
        """
        self._require_initialized()
        async with self._write_lock, self._engine.begin() as connection:
            return await self._writer.catalogue(connection, entry, generation)

    async def health(
        self, state: str, generation: int, error: str | None = None
    ) -> int:
        """Persist collector health and return its journal cursor.

        Example
        -------
        cursor = await store.health("disconnected", 1, "observer exited")
        assert (await store.events(after=cursor - 1))[0]["source"] == "collector"

        Returns
        -------
        int
            The local cursor for the health change.
        """
        self._require_initialized()
        async with self._write_lock, self._engine.begin() as connection:
            return await self._writer.health(connection, state, generation, error)

    async def snapshot(self) -> dict[str, object]:
        """Read the cursor and all projections in one SQLite read transaction.

        Example
        -------
        snapshot = await store.snapshot()
        assert snapshot["workspaceId"] == store.workspace_id

        Returns
        -------
        dict[str, object]
            The cursor-consistent workspace snapshot.
        """
        self._require_initialized()
        async with self._engine.connect() as connection, connection.begin():
            return await read_snapshot(connection, self.workspace_id)

    async def current_cursor(self) -> int:
        """Read the workspace's latest journal cursor without loading projections.

        Example
        -------
        cursor = await store.current_cursor()
        assert cursor >= 0

        Returns
        -------
        int
            The maximum local journal ID for this workspace, or zero when empty.
        """
        self._require_initialized()
        async with self._engine.connect() as connection, connection.begin():
            return await read_cursor(connection, self.workspace_id)

    async def detail(self, session_id: str) -> dict[str, object] | None:
        """Return one projection, turn records and at most 30 recent events.

        Example
        -------
        detail = await store.detail("session-1")
        assert detail is None or "session" in detail

        Returns
        -------
        dict[str, object] or None
            The session record, turns and recent events, if found.
        """
        self._require_initialized()
        async with self._engine.connect() as connection, connection.begin():
            return await read_detail(connection, self.workspace_id, session_id)

    async def events(self, after: int, limit: int = 100) -> list[dict[str, object]]:
        """Read a bounded batch of committed journal rows after ``after``.

        Example
        -------
        batch = await store.events(after=0, limit=100)
        assert all(event["cursor"] > 0 for event in batch)

        Returns
        -------
        list[dict[str, object]]
            Up to 500 committed event payloads in cursor order.
        """
        self._require_initialized()
        if limit <= 0:
            return []
        bounded_limit = min(limit, 500)
        async with self._engine.connect() as connection, connection.begin():
            return await read_events(
                connection, self.workspace_id, after, bounded_limit
            )

    def _require_initialized(self) -> None:
        """Fail clearly if an operation precedes schema initialization.

        Raises
        ------
        RuntimeError
            If ``initialize`` has not completed successfully.
        """
        if not self._initialized:
            raise RuntimeError
