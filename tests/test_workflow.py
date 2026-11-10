"""Workflow classification uses explicit PR evidence, never agent activity."""

import pytest

from ishiban.domain import PullRequest
from ishiban.workflow import classify


@pytest.mark.parametrize(
    ("title", "status", "expected"),
    [
        ("Plan: implement observer", "draft", "ready"),
        ("Plan:implement observer", "draft", "ready"),
        ("Plan: implement observer", "open", "ready"),
        ("Implement observer", "draft", "building"),
        ("Implement observer", "open", "refine"),
        (None, "draft", "unclassified"),
        (None, "merged", "merged"),
        (None, "closed", "closed"),
    ],
)
def test_explicit_pr_evidence_defines_stage(
    title: str | None, status: str, expected: str
) -> None:
    """The product's PR convention is independent of session activity."""
    pr = PullRequest(
        url="https://github.com/leynos/ishiban/pull/1", status=status, title=title
    )
    assert classify([pr]).stage == expected, (
        "Classification must follow explicit PR title and lifecycle evidence."
    )


def test_confirmed_no_pr_is_planning() -> None:
    """An explicit empty catalogue association admits the Planning stage."""
    assert classify([]).stage == "planning", (
        "A confirmed empty PR association means Planning."
    )


def test_multiple_live_prs_remain_unclassified() -> None:
    """Conflicting associations cannot silently select a workflow stage."""
    prs = [
        PullRequest(
            url=f"https://github.com/leynos/ishiban/pull/{n}",
            status="draft",
            title="Build",
        )
        for n in (1, 2)
    ]
    assert classify(prs).stage == "unclassified", (
        "Multiple active PR associations cannot choose an arbitrary workflow stage."
    )


def test_old_merged_pr_does_not_hide_the_live_association() -> None:
    """A historical merged PR does not override a unique current draft."""
    prs = [
        PullRequest(url="a", status="merged"),
        PullRequest(url="b", status="draft", title="Build"),
    ]
    assert classify(prs).stage == "building", (
        "A historical merged PR must not override the current draft."
    )


@pytest.mark.parametrize("status", ["draft", "open"])
def test_unknown_association_prevents_a_definite_active_stage(status: str) -> None:
    """An unknown association may be a second active PR."""
    prs = [
        PullRequest(
            url="https://github.com/leynos/ishiban/pull/1", status=status, title="Build"
        ),
        PullRequest(url="", status="unknown"),
    ]
    assert classify(prs).stage == "unclassified", (
        "Unknown lifecycle evidence cannot justify a unique active PR stage."
    )
