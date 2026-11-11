"""Persist lazy session runtime outside the replayable journal."""

import asyncio
import sqlite3
import time
import typing as typ

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from ishiban.protocol import SESSION_STATES
from ishiban.storage.activity_projection import (
    RUNTIME_FIELDS as RUNTIME_FIELDS,
)
from ishiban.storage.activity_projection import (
    _cache_candidate_session_id,
    _merge_projection,
    _runtime_json,
)
from ishiban.storage.database import create_engine

if typ.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

MAX_ROWS_PER_WORKSPACE = 10_000
INITIALIZE_ATTEMPTS = 5

_METADATA = sa.MetaData()
_KNOWN_STATES = SESSION_STATES - {"unknown"}
_RUNTIME_CACHE = sa.Table(
    "activity_runtime_cache",
    _METADATA,
    sa.Column("workspace_id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, primary_key=True),
    sa.Column("base_revision", sa.BigInteger, nullable=False),
    sa.Column("runtime_json", sa.Text, nullable=False),
    sa.Column("saved_at_ns", sa.BigInteger, nullable=False),
)


def _sidecar_url(journal_database_url: str) -> str:
    """Append the cache suffix to a file database while preserving memory URLs.

    For example, ``sqlite+aiosqlite:////tmp/journal.db`` maps to a sibling
    ``journal.db.activity.sqlite3`` database.

    Returns
    -------
    str
        An SQLAlchemy SQLite URL for the independent activity sidecar.
    """
    url = make_url(journal_database_url)
    if url.query.get("mode") == "memory":
        return url.set(database=":memory:", query={}).render_as_string(
            hide_password=False
        )
    if url.database is None or url.database in {"", ":memory:"}:
        return url.render_as_string(hide_password=False)
    sidecar_database = f"{url.database}.activity.sqlite3"
    return url.set(database=sidecar_database).render_as_string(hide_password=False)


def _projection_revision(projection: dict[str, object]) -> int:
    """Parse the original durable projection revision.

    Returns
    -------
    int
        Non-negative journal revision used to reject stale cache writes.

    Raises
    ------
    TypeError
        If the projection revision has an invalid type.
    ValueError
        If the projection revision is negative.
    """
    value = projection.get("lastEventId")
    match value:
        case bool():
            raise TypeError
        case int() if value < 0:
            raise ValueError
        case int():
            return value
        case str() if value.isdecimal():
            return int(value)
        case _:
            raise TypeError


def _is_retryable_open(error: OperationalError, attempt: int) -> bool:
    """Retry SQLite lock contention before the final attempt, never other errors.

    For example, a busy sidecar during the first open yields to its writer.

    Returns
    -------
    bool
        Whether this SQLite lock error has a remaining retry.
    """
    if attempt == INITIALIZE_ATTEMPTS - 1:
        return False
    if not isinstance(error.orig, sqlite3.OperationalError):
        return False
    return error.orig.sqlite_errorcode & 0xFF in {
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
    }


def _cache_values(projection: dict[str, object]) -> tuple[str, int, str]:
    """Validate the identity and known runtime before preparing a sidecar write.

    For example, an unknown source state is rejected before opening a transaction.

    Returns
    -------
    tuple[str, int, str]
        Validated identity, durable revision and encoded runtime fields.
    """
    session_id = _required_session_id(projection)
    _require_known_state(projection)
    return session_id, _projection_revision(projection), _runtime_json(projection)


def _required_session_id(projection: dict[str, object]) -> str:
    """Require a nonempty sidecar key; for example, reject a missing ID.

    Returns
    -------
    str
        The validated session identity.

    Raises
    ------
    TypeError
        If the identity is not a string.
    ValueError
        If the identity is empty.
    """
    session_id = projection.get("sessionId")
    if not isinstance(session_id, str):
        raise TypeError
    if not session_id:
        raise ValueError
    return session_id


def _require_known_state(projection: dict[str, object]) -> None:
    """Restrict sidecar writes to concrete runtime outcomes.

    Raises
    ------
    TypeError
        If the state is not a string.
    ValueError
        If the state is not a known runtime outcome.
    """
    state = projection.get("state")
    if not isinstance(state, str):
        raise TypeError
    if state not in _KNOWN_STATES:
        raise ValueError


class ActivityCache:
    """Store runtime observations in a bounded, workspace-scoped SQLite sidecar.

    For example, an unknown collector projection can recover a cached failed
    turn without changing its title or durable journal revision.
    """

    def __init__(self, journal_database_url: str, workspace_id: str) -> None:
        """Create an unopened sidecar engine for one journal and workspace.

        Parameters
        ----------
        journal_database_url : str
            Original async SQLite journal URL used to derive the sidecar path.
        workspace_id : str
            Workspace partition key stored with every runtime projection.
        """
        self.workspace_id = workspace_id
        self._engine: AsyncEngine = create_engine(_sidecar_url(journal_database_url))
        self._initialized = False

    async def initialize(self) -> None:
        """Create the cache table safely across concurrent first opens.

        For example, simultaneous API and collector startup share one sidecar.

        Raises
        ------
        sqlalchemy.exc.OperationalError
            If startup fails or SQLite remains busy after five attempts.
        """
        if self._initialized:
            return
        for attempt in range(INITIALIZE_ATTEMPTS):
            try:
                await self._create_table()
            except OperationalError as error:
                if not _is_retryable_open(error, attempt):
                    raise
                # WAL setup can contend before the idempotent DDL is reached.
                # Yield so the other connection can finish its first open.
                await asyncio.sleep(0.05)
            else:
                self._initialized = True
                return

    async def _create_table(self) -> None:
        """Create the sidecar table; for example, a concurrent open is idempotent."""
        async with self._engine.begin() as connection:
            await connection.execute(
                sa.schema.CreateTable(_RUNTIME_CACHE, if_not_exists=True)
            )

    async def close(self) -> None:
        """Dispose the sidecar engine and allow a later initialize call."""
        await self._engine.dispose()
        self._initialized = False

    async def remember(self, projection: dict[str, object]) -> None:
        """Upsert runtime evidence unless a newer durable revision is cached.

        For example, a delayed revision 7 observation cannot replace cached
        runtime for revision 8.

        Invalid identities, states and revisions fail before the SQL transaction.
        """
        self._require_initialized()
        session_id, base_revision, encoded_runtime = _cache_values(projection)
        saved_at_ns = time.time_ns()
        statement = sqlite_insert(_RUNTIME_CACHE).values(
            workspace_id=self.workspace_id,
            session_id=session_id,
            base_revision=base_revision,
            runtime_json=encoded_runtime,
            saved_at_ns=saved_at_ns,
        )
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[
                _RUNTIME_CACHE.c.workspace_id,
                _RUNTIME_CACHE.c.session_id,
            ],
            set_={
                "base_revision": excluded.base_revision,
                "runtime_json": excluded.runtime_json,
                "saved_at_ns": excluded.saved_at_ns,
            },
            where=_RUNTIME_CACHE.c.base_revision <= excluded.base_revision,
        )
        async with self._engine.begin() as connection:
            await connection.execute(upsert)
            await self._prune_workspace(connection)

    async def merge(
        self,
        projections: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Overlay cached runtime only onto eligible unknown projections.

        For example, a removed session, known state, or newer activity event
        keeps its current projection unchanged.

        Returns
        -------
        list of dict of str to object
            Copies of the input projections with eligible runtime restored.
        """
        self._require_initialized()
        eligible = {
            session_id
            for projection in projections
            if (session_id := _cache_candidate_session_id(projection)) is not None
        }
        if not eligible:
            return [dict(projection) for projection in projections]
        cached = await self._read_workspace_cache(eligible)
        merged: list[dict[str, object]] = []
        for projection in projections:
            session_id = projection.get("sessionId")
            cached_record = (
                cached.get(session_id) if isinstance(session_id, str) else None
            )
            merged.append(_merge_projection(projection, cached_record))
        return merged

    def _require_initialized(self) -> None:
        """Reject cache operations before table creation or after disposal.

        Raises
        ------
        RuntimeError
            If initialize has not completed for the current engine lifecycle.
        """
        if not self._initialized:
            raise RuntimeError

    async def _read_workspace_cache(
        self,
        session_ids: set[str],
    ) -> dict[str, tuple[int, str]]:
        """Read only requested cache keys in SQLite-safe parameter batches.

        Returns
        -------
        dict of str to tuple of int and str
            Cached base revision and runtime JSON, keyed by session ID.
        """
        records: dict[str, tuple[int, str]] = {}
        candidates = tuple(session_ids)
        async with self._engine.connect() as connection:
            for start in range(0, len(candidates), 500):
                batch = candidates[start : start + 500]
                result = await connection.execute(
                    sa.select(
                        _RUNTIME_CACHE.c.session_id,
                        _RUNTIME_CACHE.c.base_revision,
                        _RUNTIME_CACHE.c.runtime_json,
                    ).where(
                        _RUNTIME_CACHE.c.workspace_id == self.workspace_id,
                        _RUNTIME_CACHE.c.session_id.in_(batch),
                    )
                )
                records.update({
                    row.session_id: (row.base_revision, row.runtime_json)
                    for row in result
                })
        return records

    async def _prune_workspace(self, connection: AsyncConnection) -> None:
        """Delete rows beyond the workspace bound, keeping newest saves first."""
        excess_rows = (
            sa
            .select(_RUNTIME_CACHE.c.session_id)
            .where(_RUNTIME_CACHE.c.workspace_id == self.workspace_id)
            .order_by(
                _RUNTIME_CACHE.c.saved_at_ns.desc(),
                _RUNTIME_CACHE.c.session_id.asc(),
            )
            .offset(MAX_ROWS_PER_WORKSPACE)
        )
        await connection.execute(
            sa.delete(_RUNTIME_CACHE).where(
                _RUNTIME_CACHE.c.workspace_id == self.workspace_id,
                _RUNTIME_CACHE.c.session_id.in_(excess_rows),
            )
        )
