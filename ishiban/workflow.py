"""Classify workflow stages using explicit PR metadata.

For example, a draft PR titled ``Plan: observe sessions`` is Ready, while a
non-plan draft is Building. Session execution state never enters this module.
"""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from ishiban.domain import PullRequest


@dc.dataclass(frozen=True, slots=True)
class StageDecision:
    """A product stage and the evidence used to select it."""

    stage: str
    reason: str


def classify(prs: list[PullRequest]) -> StageDecision:
    """Return the stage justified by a complete catalogue association.

    Returns
    -------
    StageDecision
        The stage justified by the associated PR facts.

    Examples
    --------
    >>> classify([]).stage
    'planning'
    """
    if not prs:
        return StageDecision("planning", "Catalogue confirms no associated PR.")
    live = [pr for pr in prs if pr.status in {"draft", "open"}]
    if len(live) == 1:
        return _classify_live(live[0])
    if live:
        return StageDecision("unclassified", "Multiple active PR associations.")
    states = {pr.status for pr in prs}
    if states == {"merged"}:
        return StageDecision("merged", "All associated PRs are merged.")
    if states == {"closed"}:
        return StageDecision("closed", "Associated PRs are closed without merge.")
    return StageDecision(
        "unclassified", "PR lifecycle metadata is incomplete or conflicting."
    )


def _classify_live(pr: PullRequest) -> StageDecision:
    """Classify one active PR; for example, an untitled draft stays unknown.

    Returns
    -------
    StageDecision
        Ready, Building, Refine, or an explicit unknown classification.
    """
    if pr.title is None:
        return StageDecision(
            "unclassified",
            "PR title lookup unavailable; Plan prefix cannot be checked.",
        )
    if pr.title.startswith("Plan:"):
        return StageDecision("ready", "Associated PR title has the Plan: prefix.")
    if pr.status == "draft":
        return StageDecision("building", "Non-plan PR is a draft.")
    return StageDecision("refine", "Non-plan PR is ready for review.")
