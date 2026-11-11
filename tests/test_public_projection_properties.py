"""Generated invariants for bounded public turn previews and full-set revisions."""

import copy
import typing as typ

from hypothesis import example, given, settings
from hypothesis import strategies as st

from ishiban.public_projection import public_session

PUBLIC_PREVIEW_LIMIT = 100

TURN_STATE = st.sampled_from(["pending", "unknown", "running", "failed"])
TURN_ERROR = st.one_of(st.none(), st.text(alphabet="ab", max_size=5))
TURN_FACT = st.tuples(TURN_STATE, TURN_ERROR)
TURN_COUNT = st.one_of(
    st.sampled_from([0, 1, 99, 100, 101, 105, 120]),
    st.integers(min_value=0, max_value=120),
)


@st.composite
def turn_sets(draw: st.DrawFn, *, hidden: bool = False) -> list[dict[str, object]]:
    """Generate unique IDs and varied turn facts on both sides of the cap.

    For example, a 105-turn draw has 100 ``a`` IDs followed by five ``z`` IDs
    when ``hidden`` is true; those five cannot enter the lexical preview.

    Returns
    -------
    list of dict[str, object]
        Turns with unique identities and independently generated state/error.
    """
    count = draw(st.integers(min_value=101, max_value=120) if hidden else TURN_COUNT)
    facts = draw(st.lists(TURN_FACT, min_size=count, max_size=count))
    turns: list[dict[str, object]] = []
    for index, (state, error) in enumerate(facts):
        prefix = "z" if hidden and index >= PUBLIC_PREVIEW_LIMIT else "a"
        turns.append({
            "userTurnId": f"{prefix}-{index:03}",
            "state": state,
            "error": error,
        })
    return turns


def _preview(session: dict[str, object]) -> list[dict[str, object]]:
    """Read the public preview after the transport boundary has shaped it.

    For example, a 101-turn input returns a 100-item list here.

    Returns
    -------
    list of dict[str, object]
        The bounded public ``activeTurns`` field.
    """
    return typ.cast("list[dict[str, object]]", session["activeTurns"])


def _boundary_hidden_turns() -> list[dict[str, object]]:
    """Provide the first hidden turn at the exact 100/101 boundary.

    For example, editing ``z-100`` must change the revision without moving it
    into the 100-item preview.

    Returns
    -------
    list of dict[str, object]
        One explicit boundary case with 100 visible and one hidden turn.
    """
    return [
        {"userTurnId": f"a-{index:03}", "state": "pending", "error": None}
        for index in range(PUBLIC_PREVIEW_LIMIT)
    ] + [{"userTurnId": "z-100", "state": "failed", "error": None}]


@example(
    turns=[
        {"userTurnId": "a-000", "state": "pending", "error": None},
        {"userTurnId": "a-001", "state": "failed", "error": None},
    ],
    permutation=list(reversed(range(120))),
)
@given(turns=turn_sets(), permutation=st.permutations(range(120)))
@settings(max_examples=50, deadline=None)
def test_public_preview_conserves_full_count_and_ignores_input_order(
    turns: list[dict[str, object]], permutation: list[int]
) -> None:
    """A permutation changes neither the preview nor the full-set summary."""
    original = copy.deepcopy(turns)
    session = public_session({"activeTurns": turns})
    reordered_turns = [turns[index] for index in permutation if index < len(turns)]
    reordered = public_session({"activeTurns": reordered_turns})
    preview = _preview(session)
    assert len(preview) == min(len(turns), PUBLIC_PREVIEW_LIMIT), (
        "The public view must include exactly the bounded number of active turns."
    )
    assert session["activeTurnCount"] == len(turns), (
        "The public count must describe the complete private active set."
    )
    assert session["activeTurnsTruncated"] is (len(turns) > PUBLIC_PREVIEW_LIMIT), (
        "Truncation must disclose every hidden tail, including the 100/101 edge."
    )
    assert all(turn in turns for turn in preview), (
        "The preview must consist of original turn facts, not invented entries."
    )
    assert len({turn["userTurnId"] for turn in preview}) == len(preview), (
        "Each unique source identity must appear at most once in the preview."
    )
    assert preview == _preview(reordered), (
        "Input permutation must not reshuffle the deterministic public preview."
    )
    assert session["activeTurnsRevision"] == reordered["activeTurnsRevision"], (
        "Input permutation alone must not count as changed semantic evidence."
    )
    assert turns == original, "Public shaping must not mutate private turn facts."


@example(turns=_boundary_hidden_turns(), change_state=False)
@given(turns=turn_sets(hidden=True), change_state=st.booleans())
@settings(max_examples=40, deadline=None)
def test_hidden_fact_edit_changes_full_revision_without_preview_noise(
    turns: list[dict[str, object]], *, change_state: bool
) -> None:
    """A same-count hidden state or error edit changes the full-set revision."""
    original = public_session({"activeTurns": turns})
    changed_turns = copy.deepcopy(turns)
    hidden_turn = changed_turns[-1]
    if change_state:
        hidden_turn["state"] = (
            "failed" if hidden_turn["state"] != "failed" else "pending"
        )
    else:
        hidden_turn["error"] = "changed-hidden-error"
    changed = public_session({"activeTurns": changed_turns})
    assert _preview(original) == _preview(changed), (
        "A changed hidden turn must leave the same visible preview."
    )
    assert original["activeTurnCount"] == changed["activeTurnCount"] == len(turns), (
        "An edit to one hidden turn must preserve the full-set count."
    )
    assert original["activeTurnsRevision"] != changed["activeTurnsRevision"], (
        "A hidden semantic edit must alter the full-set revision."
    )


@given(turns=turn_sets(hidden=True))
@settings(max_examples=40, deadline=None)
def test_hidden_membership_changes_full_revision_without_preview_noise(
    turns: list[dict[str, object]],
) -> None:
    """Adding or removing a hidden turn changes the summary, not its preview."""
    original = public_session({"activeTurns": turns})
    added = public_session({
        "activeTurns": [
            *turns,
            {"userTurnId": "z-999", "state": "pending", "error": None},
        ]
    })
    removed = public_session({"activeTurns": turns[:-1]})
    assert _preview(original) == _preview(added) == _preview(removed), (
        "Changing only hidden membership must keep the visible preview stable."
    )
    assert added["activeTurnCount"] == len(turns) + 1, (
        "Adding a hidden turn must increase the exact count."
    )
    assert removed["activeTurnCount"] == len(turns) - 1, (
        "Removing a hidden turn must decrease the exact count."
    )
    assert original["activeTurnsRevision"] != added["activeTurnsRevision"], (
        "Adding a hidden turn must alter the full-set revision."
    )
    assert original["activeTurnsRevision"] != removed["activeTurnsRevision"], (
        "Removing a hidden turn must alter the full-set revision."
    )
