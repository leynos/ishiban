"""Create the append-only event journal and current projections."""

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_journal"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the initial durable observation schema."""
    op.create_table(
        "source_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("stream_id", sa.String(255)),
        sa.Column("sequence", sa.Integer()),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(255)),
        sa.Column("observed_at", sa.BigInteger()),
        sa.Column("received_at", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("projection_json", sa.Text()),
        sa.UniqueConstraint(
            "workspace_id", "stream_id", "sequence", name="uq_source_stream_sequence"
        ),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_source_events_workspace_cursor",
        "source_events",
        ["workspace_id", "id"],
    )
    op.create_index(
        "ix_source_events_session_cursor",
        "source_events",
        ["workspace_id", "session_id", "id"],
    )
    op.create_table(
        "sessions",
        sa.Column("workspace_id", sa.String(255), primary_key=True),
        sa.Column("session_id", sa.String(255), primary_key=True),
        sa.Column("machine_id", sa.String(255), nullable=False),
        sa.Column("projection_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "turns",
        sa.Column("workspace_id", sa.String(255), primary_key=True),
        sa.Column("session_id", sa.String(255), primary_key=True),
        sa.Column("user_turn_id", sa.String(255), primary_key=True),
        sa.Column("assistant_turn_id", sa.String(255)),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("last_event_id", sa.Integer(), nullable=False),
        sa.Column("projection_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["sessions.workspace_id", "sessions.session_id"],
            ondelete="CASCADE",
            name="fk_turns_session",
        ),
    )
    op.create_table(
        "collector_state",
        sa.Column("workspace_id", sa.String(255), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("last_received_at", sa.String(40)),
        sa.Column("last_event_id", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    """Remove the initial schema in foreign-key order."""
    op.drop_table("collector_state")
    op.drop_table("turns")
    op.drop_table("sessions")
    op.drop_index("ix_source_events_session_cursor", table_name="source_events")
    op.drop_index("ix_source_events_workspace_cursor", table_name="source_events")
    op.drop_table("source_events")
