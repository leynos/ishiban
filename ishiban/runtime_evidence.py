"""Choose typed runtime evidence transitions before JSON projection encoding."""

import dataclasses

from ishiban.domain import Envelope, ObservedSession, Turn


@dataclasses.dataclass(frozen=True, slots=True)
class PersistedObservation:
    """Replace runtime evidence from a verified persisted observation."""

    state: str
    latest_turn: Turn | None
    active_turns: tuple[Turn, ...]
    generation: int
    observed_at: int


@dataclasses.dataclass(frozen=True, slots=True)
class MetadataObservation:
    """Preserve prior runtime evidence and advance metadata provenance only."""

    generation: int


type ObservationPlan = PersistedObservation | MetadataObservation


@dataclasses.dataclass(frozen=True, slots=True)
class TurnPlan:
    """Set the latest turn, retire its prior versions, and optionally reopen."""

    latest_turn: Turn
    retire_user_turn_id: str
    active_turn: Turn | None
    generation: int
    observed_at: int


def plan_observation(
    observed: ObservedSession, generation: int, observed_at: int
) -> ObservationPlan:
    """Choose runtime replacement or metadata-only preservation.

    For example, a metadata refresh after a persisted failure yields only a
    metadata generation; the storage adapter keeps the earlier failed turn.

    Returns
    -------
    ObservationPlan
        Typed evidence to apply without coupling policy to public JSON keys.
    """
    if observed.source != "persisted":
        return MetadataObservation(generation)
    return PersistedObservation(
        state=observed.state,
        latest_turn=observed.latest_turn,
        active_turns=tuple(observed.active_turns),
        generation=generation,
        observed_at=observed_at,
    )


def plan_turn(envelope: Envelope, generation: int) -> TurnPlan:
    """Choose one named turn transition without inferring session activity.

    For example, finishing an unseen turn still sets the latest terminal turn;
    starting the same identity later retires its old active version.

    Returns
    -------
    TurnPlan
        Typed latest and active turns with the retirement identity and time.
    """
    is_start = envelope.type == "turn.started"
    state = "running" if is_start else envelope.outcome or "unknown"
    user_turn_id = envelope.user_turn_id or ""
    latest = Turn(
        user_turn_id=user_turn_id,
        state=state,
        assistant_turn_id=envelope.assistant_turn_id,
        duration_ms=envelope.duration_ms,
        error=envelope.error if state == "failed" else None,
    )
    return TurnPlan(
        latest_turn=latest,
        retire_user_turn_id=user_turn_id,
        active_turn=latest if is_start else None,
        generation=generation,
        observed_at=envelope.observed_at,
    )
