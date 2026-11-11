"""Mixed journal histories preserve runtime evidence across metadata and restarts."""

import dataclasses
import tempfile
import typing as typ
from pathlib import Path

import hypothesis
import pytest
from hypothesis import strategies as st
from storage_support import EventOptions, as_snapshot, envelope, opened_store

from ishiban.domain import CatalogueEntry, ObservedSession, Turn

if typ.TYPE_CHECKING:
    from ishiban.storage import Store

OBSERVED_AT_BASE = 1_700_000_000_000


@dataclasses.dataclass(frozen=True, slots=True)
class Action:
    """Choose one valid journal operation for a generated history."""

    kind: str
    value: str = ""
    turn_id: str = "u1"


ACTIONS = (
    Action("restart"),
    Action("metadata"),
    Action("catalogue", "planning"),
    Action("catalogue", "ready"),
    Action("persisted", "unknown"),
    Action("persisted", "idle"),
    Action("persisted", "running"),
    Action("start", turn_id="u1"),
    Action("start", turn_id="u2"),
    Action("finish", "failed", "u1"),
    Action("finish", "completed", "u1"),
    Action("finish", "failed", "u2"),
    Action("finish", "completed", "u2"),
)


@dataclasses.dataclass(slots=True)
class ExpectedRuntime:
    """Track only the externally visible evidence contract, independent of storage."""

    generation: int = 1
    state: str = "idle"
    latest_turn: tuple[str, str] | None = ("u1", "failed")
    active_turns: dict[str, str] = dataclasses.field(default_factory=dict)
    source: str = "persisted"
    evidence_generation: int | None = 1
    metadata_generation: int | None = None
    observed_at: int | None = OBSERVED_AT_BASE + 1
    activity_event_id: int = 0
    stage: str = "unclassified"
    repo: str | None = None


def _observed_for(value: str) -> ObservedSession:
    """Supply a persisted replacement with distinct known and unknown facts.

    For example, ``running`` carries an active u2 turn while ``unknown`` does
    not claim a latest turn.

    Returns
    -------
    ObservedSession
        One complete persisted observer record for the fixed session.
    """
    latest = None
    active: list[Turn] = []
    match value:
        case "running":
            latest = Turn("u2", "running")
            active = [latest]
        case "idle":
            latest = Turn("u1", "failed")
    return ObservedSession(
        session_id="s1",
        machine_id="m1",
        title="Persisted observation",
        state=value,
        source="persisted",
        freshness="synced",
        latest_turn=latest,
        active_turns=active,
    )


async def _apply_to_store(
    store: Store, action: Action, generation: int, sequence: int
) -> int | None:
    """Send one action through the real store and return its evidence cursor.

    Returns
    -------
    int or None
        Event cursor, or no event cursor for a generation restart.
    """
    match action.kind:
        case "restart":
            await store.begin_generation()
            return None
        case "catalogue":
            return await store.catalogue(
                CatalogueEntry(
                    session_id="s1",
                    machine_id="m1",
                    title=f"Catalogue {action.value}",
                    archived=False,
                    repo_full_name=f"leynos/{action.value}",
                    branch_name="main",
                    pull_requests=[],
                    stage=action.value,
                    stage_reason="Explicit catalogue evidence.",
                ),
                generation,
            )
        case "persisted":
            options = EventOptions(session=_observed_for(action.value))
        case "metadata":
            options = EventOptions(
                session=ObservedSession(
                    session_id="s1",
                    machine_id="m1",
                    title="Metadata observation",
                    state="unknown",
                    source="metadata",
                    freshness="unavailable",
                )
            )
        case _:
            is_start = action.kind == "start"
            options = EventOptions(
                event_type="turn.started" if is_start else "turn.finished",
                user_turn_id=action.turn_id,
                outcome=None if is_start else action.value,
            )
    return await store.ingest(envelope(sequence, options=options), generation)


def _advance_persisted(
    expected: ExpectedRuntime, action: Action, cursor: int | None
) -> None:
    """Replace the model's runtime facts from one complete persisted snapshot."""
    expected.state = action.value
    match action.value:
        case "running":
            expected.latest_turn = ("u2", "running")
            expected.active_turns = {"u2": "running"}
        case "idle":
            expected.latest_turn = ("u1", "failed")
            expected.active_turns = {}
        case _:
            expected.latest_turn = None
            expected.active_turns = {}
    if action.value != "unknown" and cursor is not None:
        expected.activity_event_id = cursor


def _advance_turn(
    expected: ExpectedRuntime, action: Action, cursor: int | None
) -> None:
    """Retire a named active turn and retain the newest terminal or running fact."""
    state = "running" if action.kind == "start" else action.value
    expected.latest_turn = (action.turn_id, state)
    expected.active_turns.pop(action.turn_id, None)
    if action.kind == "start":
        expected.active_turns[action.turn_id] = "running"
    if cursor is not None:
        expected.activity_event_id = cursor


def _advance_expected(
    expected: ExpectedRuntime, action: Action, sequence: int, cursor: int | None
) -> None:
    """Apply the history's observable rule without calling production policy."""
    match action.kind:
        case "restart":
            expected.generation += 1
            return
        case "catalogue":
            expected.stage = action.value
            expected.repo = f"leynos/{action.value}"
            expected.metadata_generation = expected.generation
            return
        case "metadata":
            expected.source = "metadata"
            expected.metadata_generation = expected.generation
            return
    expected.source = "persisted"
    expected.evidence_generation = expected.generation
    expected.observed_at = OBSERVED_AT_BASE + sequence
    if action.kind == "persisted":
        _advance_persisted(expected, action, cursor)
    else:
        _advance_turn(expected, action, cursor)


async def _assert_prefix(store: Store, expected: ExpectedRuntime) -> None:
    """Compare each committed prefix with the independent evidence model."""
    snapshot = as_snapshot(await store.snapshot())
    assert len(snapshot["sessions"]) == 1, "Every prefix retains the seeded session."
    actual = snapshot["sessions"][0]
    assert actual["state"] == expected.state, "Metadata cannot invent runtime state."
    assert actual["source"] == expected.source, "Provenance follows the last source."
    assert actual["lastEvidenceGeneration"] == expected.evidence_generation, (
        "Only runtime evidence advances its generation."
    )
    assert actual["lastMetadataGeneration"] == expected.metadata_generation, (
        "Only metadata or catalogue updates advance metadata generation."
    )
    assert actual["lastObservedAt"] == expected.observed_at, (
        "Metadata and restarts cannot replace the last runtime observation time."
    )
    assert actual.get("lastActivityEventId", 0) == expected.activity_event_id, (
        "Only known persisted states and turn transitions advance activity."
    )
    assert actual["stage"] == expected.stage, "Turn evidence cannot infer PR stage."
    assert actual["repoFullName"] == expected.repo, (
        "Runtime evidence cannot replace catalogue repository context."
    )
    latest = actual["latestTurn"]
    latest_pair = None if latest is None else (latest["userTurnId"], latest["state"])
    assert latest_pair == expected.latest_turn, (
        "The latest turn follows a persisted snapshot or named transition."
    )
    active = [(turn["userTurnId"], turn["state"]) for turn in actual["activeTurns"]]
    assert active == list(expected.active_turns.items()), (
        "Only starts remain active; persisted observations replace the active set."
    )


@hypothesis.example(
    actions=[Action("metadata"), Action("catalogue", "ready"), Action("restart")]
)
@hypothesis.example(
    actions=[
        Action("restart"),
        Action("finish", "completed", "u2"),
        Action("metadata"),
        Action("start", turn_id="u2"),
        Action("restart"),
        Action("catalogue", "planning"),
    ]
)
@hypothesis.given(actions=st.lists(st.sampled_from(ACTIONS), min_size=1, max_size=12))
@hypothesis.settings(max_examples=40, deadline=None)
@pytest.mark.asyncio
async def test_mixed_runtime_history_prefixes_match_independent_model(
    actions: list[Action],
) -> None:
    """Every mixed prefix preserves or replaces evidence by explicit source kind."""
    with tempfile.TemporaryDirectory() as directory:
        async with opened_store(Path(directory)) as store:
            generation = await store.begin_generation()
            seed_cursor = await store.ingest(
                envelope(1, options=EventOptions(session=_observed_for("idle"))),
                generation,
            )
            expected = ExpectedRuntime(activity_event_id=seed_cursor)
            await _assert_prefix(store, expected)
            for sequence, action in enumerate(actions, start=2):
                cursor = await _apply_to_store(store, action, generation, sequence)
                _advance_expected(expected, action, sequence, cursor)
                generation = expected.generation
                await _assert_prefix(store, expected)
