"""Keep runtime evidence decisions separate from legacy JSON projection shape."""

import msgspec

from ishiban.domain import Envelope, ObservedSession, Turn
from ishiban.runtime_evidence import (
    MetadataObservation,
    PersistedObservation,
    plan_observation,
    plan_turn,
)
from ishiban.storage.projections import apply_observation, apply_turn_event


def test_observation_plan_preserves_metadata_and_snapshots_persisted_turns() -> None:
    """Metadata has no replacement evidence; persisted input owns a stable tuple."""
    active = Turn("u1", "running")
    observed = ObservedSession(
        session_id="s1",
        source="persisted",
        state="running",
        latest_turn=active,
        active_turns=[active],
    )
    persisted = plan_observation(observed, generation=4, observed_at=95)
    assert isinstance(persisted, PersistedObservation), (
        "Persisted source evidence must produce a replacement plan."
    )
    assert persisted == PersistedObservation(
        state="running",
        latest_turn=active,
        active_turns=(active,),
        generation=4,
        observed_at=95,
    ), "The replacement plan must carry the source state and evidence watermark."
    observed.active_turns.clear()
    assert persisted.active_turns == (active,), (
        "A later source-list mutation cannot change an already chosen plan."
    )

    metadata = plan_observation(
        ObservedSession(session_id="s1", source="metadata", state="idle"),
        generation=5,
        observed_at=96,
    )
    assert metadata == MetadataObservation(generation=5), (
        "Metadata cannot assert a runtime state or observation time."
    )


def test_turn_plan_selects_retirement_and_new_active_version() -> None:
    """Start reopens an identity; finish retires it without requiring a start."""
    event = Envelope(
        version=1,
        stream_id="stream",
        sequence=1,
        observed_at=95,
        workspace_id="w1",
        type="turn.started",
        user_turn_id="u1",
        assistant_turn_id="a2",
        error="prior failure",
    )
    started = plan_turn(event, generation=4)
    assert started.retire_user_turn_id == "u1", (
        "A new start retires any prior active version of its stable ID."
    )
    assert started.latest_turn == Turn("u1", "running", "a2"), (
        "A reopened running turn must drop stale failure details."
    )
    assert started.active_turn == started.latest_turn, (
        "A start adds the newly selected latest turn to active evidence."
    )
    assert started.generation == 4, "The plan keeps its supplied generation."
    assert started.observed_at == 95, "The plan keeps the event observation time."

    finished = plan_turn(
        msgspec.structs.replace(event, type="turn.finished", outcome="completed"),
        generation=5,
    )
    assert finished.retire_user_turn_id == "u1", (
        "A finish retires active versions of its stable ID."
    )
    assert finished.latest_turn.state == "completed", (
        "A finish sets its terminal outcome even without a prior start."
    )
    assert finished.active_turn is None, "A finished turn cannot remain active."


def test_facade_preserves_legacy_active_values_and_unrelated_fields() -> None:
    """A turn retires matching IDs without normalizing opaque legacy items."""
    previous: dict[str, object] = {
        "sessionId": "s1",
        "activeTurns": [
            {"userTurnId": "u1", "state": "running", "extra": "old"},
            {"userTurnId": "u2", "state": "running", "extra": "keep"},
            "legacy malformed item",
        ],
        "stage": "review",
        "opaque": {"legacy": True},
    }
    event = Envelope(
        version=1,
        stream_id="stream",
        sequence=1,
        observed_at=95,
        workspace_id="w1",
        type="turn.started",
        session_id="s1",
        user_turn_id="u1",
    )
    result = apply_turn_event(previous, event, generation=4)
    previous_active = previous["activeTurns"]
    current_active = result["activeTurns"]
    assert isinstance(previous_active, list), "The fixture needs legacy list values."
    assert isinstance(current_active, list), "Turn starts must publish an active list."
    assert len(current_active) == 3, (
        "Retiring one version and starting another must retain exactly three items."
    )
    assert current_active[:2] == previous_active[1:], (
        "Unrelated and malformed legacy siblings must retain their original shape."
    )
    assert current_active[-1] == {"userTurnId": "u1", "state": "running"}, (
        "The new active version replaces the retired version of that ID."
    )
    assert result["stage"] == "review", "Turn events cannot infer PR stage."
    assert result["opaque"] == {"legacy": True}, (
        "Turn events must copy unrelated projection fields."
    )
    assert previous["activeTurns"][0] == {
        "userTurnId": "u1",
        "state": "running",
        "extra": "old",
    }, "Projection updates cannot mutate their decoded source object."

    previous["activeTurns"] = {"malformed": "value"}
    from_non_list = apply_turn_event(previous, event, generation=5)
    assert from_non_list["activeTurns"] == [{"userTurnId": "u1", "state": "running"}], (
        "A non-list legacy field is treated as empty before the start append."
    )


def test_facade_keeps_optional_turn_shape_and_evidence_generations() -> None:
    """Metadata preserves evidence; failed errors remain bounded and optional."""
    previous = apply_observation(
        None,
        ObservedSession(
            session_id="s1",
            source="persisted",
            state="idle",
            latest_turn=Turn("u1", "failed", error="x" * 5000),
        ),
        generation=4,
        observed_at=95,
    )
    previous["opaque"] = "keep"
    metadata = apply_observation(
        previous,
        ObservedSession(session_id="s1", source="metadata", state="running"),
        generation=5,
        observed_at=96,
    )
    assert metadata["state"] == "idle", "Metadata cannot replace runtime state."
    assert metadata["lastEvidenceGeneration"] == 4, (
        "Metadata cannot advance the evidence generation."
    )
    assert metadata["lastObservedAt"] == 95, (
        "Metadata cannot replace the last evidence observation time."
    )
    assert metadata["lastMetadataGeneration"] == 5, (
        "Metadata advances only its own provenance generation."
    )
    assert metadata["opaque"] == "keep", (
        "Metadata refresh preserves unrelated projection fields."
    )
    assert metadata["latestTurn"] == {
        "userTurnId": "u1",
        "state": "failed",
        "error": "x" * 4096,
    }, "Metadata refresh retains the bounded failed-turn diagnostic."
    assert previous["lastMetadataGeneration"] is None, (
        "Projection updates cannot mutate the prior metadata generation."
    )
