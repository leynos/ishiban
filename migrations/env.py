"""Alembic runtime configuration for Ishiban's SQLite schema."""

from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context

from ishiban.storage.models import metadata

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url"),
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations through an injected connection or standalone sync engine."""
    connection = context.config.attributes.get("connection")
    if connection is None:
        engine = sa.engine_from_config(
            context.config.get_section(context.config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=sa.pool.NullPool,
        )
        with engine.connect() as standalone_connection:
            _run_with_connection(standalone_connection)
        engine.dispose()
        return
    _run_with_connection(connection)


def _run_with_connection(connection: sa.Connection) -> None:
    """Run the migration context for an existing synchronous connection."""
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
