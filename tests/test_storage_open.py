"""Reader-process initialization contracts for existing SQLite stores."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from storage_support import as_snapshot

from ishiban.storage import Store


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


def test_standalone_alembic_targets_repository_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Standalone migrations use a synchronous driver and the repository state."""
    repository = Path(__file__).parents[1]
    config_path = tmp_path / "alembic.ini"
    config_path.write_text(
        (repository / "alembic.ini").read_text(encoding="utf-8"), encoding="utf-8"
    )
    state = tmp_path / ".ishiban"
    state.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    config = Config(str(config_path))
    config.set_main_option("script_location", str(repository / "migrations"))

    command.upgrade(config, "head")

    database = state / "observatory.sqlite3"
    assert database.exists(), "Standalone migrations must target repository state."
    assert not (unrelated / "ishiban.db").exists(), (
        "The caller's working directory must not select the database."
    )
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        assert revision == "0001_initial_journal", (
            "Standalone migrations must apply the real schema head."
        )
    finally:
        engine.dispose()
