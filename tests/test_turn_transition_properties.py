"""Generated turn histories check domain plans against journal projections."""

import copy
import typing as typ

from hypothesis import example, given, settings
from hypothesis import strategies as st

from ishiban.domain import Envelope
from ishiban.runtime_evidence import plan_turn
from ishiban.storage.projections import (
    SessionProjection,
    apply_turn_event,
    empty_session,
)

TURN_IDS = ("u1", "u2", "u3", "u4")
OUTCOMES = ("completed", "failed", "canceled")
TURN_ACTIONS = st.one_of(
    st.tuples(st.sampled_from(TURN_IDS), st.just("turn.started"), st.none()),
    st.tuples(
        st.sampled_from(TURN_IDS),
        st.just("turn.finished"),
        st.sampled_from(OUTCOMES),
    ),
)
type TurnOperation = tuple[str, str, str | None]


def _envelope_for(operation: TurnOperation, sequence: int) -> Envelope:
    """Build a valid event for one generated operation in this property suite.

    For example, a failed finish carries a diagnostic; a start has no outcome.

    Returns
    -------
    Envelope
        A version-one turn event with bounded identity and evidence fields.
    """
    turn_id, event_type, outcome = operation
    return Envelope(
        version=1,
        stream_id="turns",
        sequence=sequence,
        observed_at=sequence * 10,
        workspace_id="w1",
        type=event_type,
        session_id="s1",
        user_turn_id=turn_id,
        assistant_turn_id=f"a{sequence}",
        outcome=outcome,
        duration_ms=sequence if event_type == "turn.finished" else None,
        error=f"failure-{sequence}" if outcome == "failed" else None,
    )


def _assert_plan(envelope: Envelope, generation: int) -> None:
    """Check that the domain plan uses this event's identity and outcome."""
    plan = plan_turn(envelope, generation)
    expected_state = "running" if envelope.type == "turn.started" else envelope.outcome
    assert plan.retire_user_turn_id == envelope.user_turn_id, (
        "A transition must retire any earlier active version of its identity."
    )
    assert plan.latest_turn.user_turn_id == envelope.user_turn_id, (
        "The plan's latest turn must name the event identity."
    )
    assert plan.latest_turn.state == expected_state, (
        "The plan must use the start or terminal outcome from this event."
    )
    assert (plan.active_turn is not None) == (envelope.type == "turn.started"), (
        "Only a start can keep its turn active in the domain plan."
    )
    assert plan.latest_turn.error == envelope.error, (
        "Only a failed latest turn may retain its supplied diagnostic."
    )


def _assert_active_turns(
    projection: SessionProjection, history: list[TurnOperation]
) -> None:
    """Compare active IDs with the last operation for each stable identity."""
    last_operation = {identity: kind for identity, kind, _ in history}
    expected_active = {
        identity for identity, kind in last_operation.items() if kind == "turn.started"
    }
    active_turns = projection["activeTurns"]
    assert isinstance(active_turns, list), (
        "The projection must expose active turns as a list."
    )
    active_ids = [
        typ.cast("dict[str, object]", item)["userTurnId"]
        for item in active_turns
        if isinstance(item, dict)
    ]
    assert len(active_ids) == len(active_turns), (
        "Every active turn must have a projection record."
    )
    assert len(active_ids) == len(set(active_ids)), (
        "Repeated starts cannot create duplicate active identities."
    )
    assert set(active_ids) == expected_active, (
        "Active identities must match the last operation for each turn ID."
    )
    assert all(
        typ.cast("dict[str, object]", item).get("state") == "running"
        for item in active_turns
        if isinstance(item, dict)
    ), "Every active turn must describe a running turn."


def _assert_latest_and_context(
    projection: SessionProjection, envelope: Envelope, generation: int
) -> None:
    """Check latest outcome and that turn evidence leaves session context alone."""
    latest_value = projection["latestTurn"]
    assert isinstance(latest_value, dict), "Every turn event must set a latest turn."
    latest = typ.cast("dict[str, object]", latest_value)
    expected_state = "running" if envelope.type == "turn.started" else envelope.outcome
    assert latest["userTurnId"] == envelope.user_turn_id, (
        "The latest projection must follow the most recent event identity."
    )
    assert latest["state"] == expected_state, (
        "The latest projection must expose the most recent event outcome."
    )
    assert latest["assistantTurnId"] == envelope.assistant_turn_id, (
        "The latest projection must preserve the source assistant identity."
    )
    assert latest.get("error") == envelope.error, (
        "A reopened or successful turn cannot inherit a failure diagnostic."
    )
    assert projection["state"] == "idle", (
        "Turn transitions must not infer session activity from a turn outcome."
    )
    assert projection["stage"] == "refine", (
        "Turn transitions must not infer the PR workflow stage."
    )
    assert projection["lastEvidenceGeneration"] == generation, (
        "Each transition must record its supplied evidence generation."
    )


@example(operations=[("u1", "turn.finished", "failed")])
@example(operations=[("u1", "turn.started", None)] * 2)
@example(
    operations=[
        ("u1", "turn.started", None),
        ("u1", "turn.finished", "failed"),
        ("u1", "turn.started", None),
    ]
)
@example(
    operations=[
        ("u1", "turn.started", None),
        ("u2", "turn.started", None),
        ("u1", "turn.finished", "canceled"),
        ("u2", "turn.started", None),
    ]
)
@given(operations=st.lists(TURN_ACTIONS, min_size=1, max_size=30))
@settings(max_examples=100, deadline=None)
def test_turn_history_prefixes_match_last_operation_per_identity(
    operations: list[TurnOperation],
) -> None:
    """Every prefix has one current turn per active identity and no inferred stage."""
    projection = empty_session("s1")
    projection["state"] = "idle"
    projection["stage"] = "refine"

    for sequence, operation in enumerate(operations, start=1):
        envelope = _envelope_for(operation, sequence)
        _assert_plan(envelope, sequence)
        original = projection
        prior = copy.deepcopy(original)
        projection = apply_turn_event(original, envelope, generation=sequence)
        assert original == prior, (
            "Applying a turn must leave its input projection unchanged."
        )
        _assert_active_turns(projection, operations[:sequence])
        _assert_latest_and_context(projection, envelope, sequence)
