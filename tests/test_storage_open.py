"""Reader-process initialization contracts for existing SQLite stores."""

import typing as typ

import pytest
from sqlalchemy import text
from storage_support import as_snapshot

from ishiban.storage import Store

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_reader_open_verifies_schema_without_running_migrations(
    tmp_path: Path,
) -> None:
    """A reader opens a migrated database and retains its committed cursor."""
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'reader.sqlite3'}"
    writer = Store(database_url, "w1")
    reader = Store(database_url, "w1")
    try:
        await writer.initialize()
        await writer.begin_generation()
        await writer.close()

        await reader.initialize(migrate=False)
        snapshot = as_snapshot(await reader.snapshot())
    finally:
        await writer.close()
        await reader.close()

    assert snapshot["cursor"] == 1, (
        "A reader opens a migrated database and retains its committed cursor."
    )
    assert snapshot["collector"]["state"] == "connecting", (
        "A reader opens a migrated database and retains its committed cursor."
    )


@pytest.mark.asyncio
async def test_reader_open_rejects_an_unmigrated_database_without_creating_tables(
    tmp_path: Path,
) -> None:
    """A reader fails closed instead of upgrading an empty database."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'empty.sqlite3'}", "w1")
    try:
        with pytest.raises(RuntimeError):
            await store.initialize(migrate=False)
        async with store._engine.connect() as connection:
            table_count = await connection.scalar(
                text("SELECT count(*) FROM sqlite_master WHERE type = 'table'")
            )
    finally:
        await store.close()

    assert table_count == 0, (
        "A reader fails closed instead of upgrading an empty database."
    )
