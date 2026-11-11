"""SQLite connection configuration and Alembic schema initialization."""

import typing as typ
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine

if typ.TYPE_CHECKING:
    import sqlite3

    from sqlalchemy.ext.asyncio import AsyncEngine

EXPECTED_SCHEMA_HEAD = "0001_initial_journal"


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLite engine with explicit transaction semantics.

    Returns
    -------
    AsyncEngine
        The configured engine for the supplied SQLite URL.

    Raises
    ------
    ValueError
        If ``database_url`` does not select the async SQLite dialect.
    """
    if not database_url.startswith("sqlite+aiosqlite:"):
        raise ValueError

    engine = create_async_engine(database_url, connect_args={"timeout": 5.0})

    @sa_event.listens_for(engine.sync_engine, "connect")
    def configure_connection(dbapi_connection: object, _: object) -> None:
        """Set SQLite pragmas before the connection's first transaction."""
        connection = typ.cast("sqlite3.Connection", dbapi_connection)
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @sa_event.listens_for(engine.sync_engine, "begin")
    def begin_transaction(connection: sa.Connection) -> None:
        """Make SQLAlchemy transaction boundaries explicit to SQLite."""
        connection.exec_driver_sql("BEGIN")

    return engine


async def initialize_schema(engine: AsyncEngine) -> None:
    """Apply packaged migrations, or the source tree's canonical scripts."""
    package_root = Path(__file__).parents[1]
    packaged_migrations = package_root / "migrations"
    if packaged_migrations.is_dir():
        alembic_config = Config()
        script_location = packaged_migrations
    else:
        repository_root = package_root.parent
        alembic_config = Config(str(repository_root / "alembic.ini"))
        script_location = repository_root / "migrations"
    alembic_config.set_main_option("script_location", str(script_location))

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade_schema, alembic_config)


async def verify_schema(engine: AsyncEngine) -> None:
    """Verify the database is at the expected Alembic head without writing.

    Raises
    ------
    RuntimeError
        If the Alembic version table is missing or out of date.
    """
    async with engine.connect() as connection:
        version_table = await connection.scalar(
            sa.text(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'alembic_version'"
            )
        )
        if version_table != 1:
            raise RuntimeError
        version = await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version LIMIT 1")
        )
    if version != EXPECTED_SCHEMA_HEAD:
        raise RuntimeError


def _upgrade_schema(connection: sa.Connection, config: Config) -> None:
    """Run Alembic against the async engine's synchronous connection."""
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
