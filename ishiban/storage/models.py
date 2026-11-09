"""SQLAlchemy schema metadata for the durable observation journal."""

import sqlalchemy as sa

metadata = sa.MetaData()

source_events = sa.Table(
    "source_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("workspace_id", sa.String(255), nullable=False),
    sa.Column("stream_id", sa.String(255)),
    sa.Column("sequence", sa.Integer),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("event_type", sa.String(64), nullable=False),
    sa.Column("session_id", sa.String(255)),
    sa.Column("observed_at", sa.BigInteger),
    sa.Column("received_at", sa.String(40), nullable=False),
    sa.Column("payload_json", sa.Text, nullable=False),
    sa.Column("projection_json", sa.Text),
    sa.UniqueConstraint(
        "workspace_id", "stream_id", "sequence", name="uq_source_stream_sequence"
    ),
    sqlite_autoincrement=True,
)

sessions = sa.Table(
    "sessions",
    metadata,
    sa.Column("workspace_id", sa.String(255), primary_key=True),
    sa.Column("session_id", sa.String(255), primary_key=True),
    sa.Column("machine_id", sa.String(255), nullable=False),
    sa.Column("projection_json", sa.Text, nullable=False),
)

turns = sa.Table(
    "turns",
    metadata,
    sa.Column("workspace_id", sa.String(255), primary_key=True),
    sa.Column("session_id", sa.String(255), primary_key=True),
    sa.Column("user_turn_id", sa.String(255), primary_key=True),
    sa.Column("assistant_turn_id", sa.String(255)),
    sa.Column("state", sa.String(64), nullable=False),
    sa.Column("duration_ms", sa.Integer),
    sa.Column("last_event_id", sa.Integer, nullable=False),
    sa.Column("projection_json", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["workspace_id", "session_id"],
        ["sessions.workspace_id", "sessions.session_id"],
        ondelete="CASCADE",
        name="fk_turns_session",
    ),
)

collector_state = sa.Table(
    "collector_state",
    metadata,
    sa.Column("workspace_id", sa.String(255), primary_key=True),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("last_error", sa.String(500)),
    sa.Column("last_received_at", sa.String(40)),
    sa.Column("last_event_id", sa.Integer, nullable=False),
)
