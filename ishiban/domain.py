"""Validated domain records exchanged between the observer and storage."""

import msgspec as ms


class Turn(ms.Struct, rename="camel"):
    """Describe the latest known state for one stable user-turn identity."""

    user_turn_id: str
    state: str
    assistant_turn_id: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class ObservedSession(ms.Struct, rename="camel"):
    """Represent one bounded session projection from the Lody observer."""

    session_id: str
    machine_id: str = ""
    title: str = ""
    archived: bool = False
    state: str = "unknown"
    source: str = "metadata"
    freshness: str = "unavailable"
    latest_turn: Turn | None = None
    active_turns: list[Turn] = ms.field(default_factory=list)


class Envelope(ms.Struct, rename="camel"):
    """Represent one validated version-one event from the observation stream."""

    version: int
    stream_id: str
    sequence: int
    observed_at: int
    workspace_id: str
    type: str
    session_id: str | None = None
    session: ObservedSession | None = None
    user_turn_id: str | None = None
    assistant_turn_id: str | None = None
    outcome: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class PullRequest(ms.Struct, rename="camel"):
    """Describe a pull request associated with a session catalogue record."""

    url: str
    status: str
    title: str | None = None


class CatalogueEntry(ms.Struct, rename="camel"):
    """Represent the latest read-only catalogue enrichment for one session."""

    session_id: str
    machine_id: str
    title: str
    archived: bool
    repo_full_name: str | None
    branch_name: str | None
    pull_requests: list[PullRequest]
    stage: str
    stage_reason: str
    parent_session_id: str | None = None
    created_at: str | None = None
