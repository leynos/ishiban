"""Static public projection contracts for storage assertions."""

import typing as typ

class TurnProjection(typ.TypedDict, total=False):
    """Describe the public turn projection fields asserted by storage tests."""

    userTurnId: str
    state: str
    assistantTurnId: str
    durationMs: int
    lastEventId: int

class Projection(typ.TypedDict, total=False):
    """Describe the public projection fields asserted by storage tests."""

    state: str
    source: str
    freshness: str
    generation: int
    lastEventId: int
    title: str
    repoFullName: str | None
    removed: bool
    stage: str
    lastEvidenceGeneration: int | None
    lastMetadataGeneration: int | None
    lastObservedAt: int | None
    latestTurn: TurnProjection | None
    activeTurns: list[TurnProjection]

class Snapshot(typ.TypedDict):
    """Describe the public snapshot fields asserted by storage tests."""

    cursor: int
    collector: Projection
    sessions: list[Projection]

class Event(typ.TypedDict):
    """Describe the public event fields asserted by storage tests."""

    cursor: int
    source: str
    projection: Projection

class RecentEvent(typ.TypedDict):
    """Describe the public recent-event fields asserted by storage tests."""

    cursor: int
    source: str
    eventType: str
    observedAt: int | None

class Detail(typ.TypedDict):
    """Describe the public detail fields asserted by storage tests."""

    session: Projection
    turns: list[TurnProjection]
    recentEvents: list[RecentEvent]
