"""PR and main coverage share a measured, migration-aware toolchain."""

import pathlib
import typing as typ

import pytest
import yaml

ROOT = pathlib.Path(__file__).parents[1]


def _coverage_job(
    workflow: str, job_name: str
) -> tuple[dict[str, typ.Any], dict[str, typ.Any], dict[str, typ.Any]]:
    """Load one workflow's coverage action; for example, inspect main.

    Returns
    -------
    tuple[dict, dict, dict]
        The workflow, selected job, and pinned coverage action.
    """
    definition = yaml.safe_load(
        (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    )
    job = definition["jobs"][job_name]
    action = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith(
            "leynos/shared-actions/.github/actions/generate-coverage@"
        )
    )
    return definition, job, action


@pytest.mark.parametrize(
    ("workflow", "job"),
    [("ci.yml", "lint-test"), ("coverage-main.yml", "coverage-upload")],
    ids=["pull-request", "main-publisher"],
)
def test_coverage_lanes_share_instrumentation_contract(workflow: str, job: str) -> None:
    """Compatible serial instrumentation retains the existing ratchet and scope."""
    _, _, step = _coverage_job(workflow, job)
    workers = step["with"]["pytest-workers"]
    assert isinstance(workers, str), "The action worker input must be a string."
    assert not workers, "Dynamic migrations require the verified serial coverage path."
    assert step["with"]["with-ratchet"] == "true", (
        "The coverage ratchet must remain enabled."
    )
    assert "python-source" not in step["with"], (
        "The authorized baseline reset must not silently change measurement scope."
    )
    assert step["env"]["UV_CONSTRAINT"] == (
        "${{ github.workspace }}/.github/coverage-constraints.txt"
    ), "Both publishers must constrain the coverage action's separate pip install."
    assert (
        "error:Unable to activate pytest branch coverage"
        in step["env"]["PYTHONWARNINGS"]
    ), "Unsupported pytest hooks must fail instead of losing instrumentation."


def test_coverage_dependencies_pin_the_verified_compatible_versions() -> None:
    """The measured version tuple must survive the action's dependency installation."""
    requirements = set(
        (ROOT / ".github" / "coverage-constraints.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert {
        "pytest==9.1.0",
        "slipcover==1.1.0",
        "pytest-xdist==3.8.0",
        "coverage==7.17.2",
    } <= requirements, (
        "Coverage baseline and publisher must use the verified version tuple."
    )


def test_main_coverage_publishes_a_baseline_for_main_dispatch() -> None:
    """A manual main run must establish the PR baseline after an automerge."""
    definition, job, action = _coverage_job("coverage-main.yml", "coverage-upload")
    triggers = definition.get("on", definition.get(True))
    assert "workflow_dispatch" in triggers, (
        "Automerge needs a manual main publisher when its token suppresses push CI."
    )
    assert "push" in triggers, (
        "Automerge needs a manual main publisher when its token suppresses push CI."
    )
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}", (
        "A manual dispatch from a feature branch must not publish its coverage as main."
    )
    assert action["with"]["publish-baseline"] == "always", (
        "The shared action must save the measured baseline on manual main runs."
    )
    _, _, pr_action = _coverage_job("ci.yml", "lint-test")
    assert "publish-baseline" not in pr_action["with"], (
        "Pull-request measurements must never overwrite main's baseline."
    )


@pytest.mark.parametrize(
    ("workflow", "job_name", "event_context", "expected_policy"),
    [
        (
            "coverage-main.yml",
            "coverage-upload",
            ("push", "refs/heads/main"),
            "publish",
        ),
        (
            "coverage-main.yml",
            "coverage-upload",
            ("workflow_dispatch", "refs/heads/main"),
            "publish",
        ),
        (
            "coverage-main.yml",
            "coverage-upload",
            ("workflow_dispatch", "refs/heads/feature"),
            "skip",
        ),
        ("ci.yml", "lint-test", ("pull_request", "refs/pull/9/merge"), "skip"),
    ],
    ids=["push-main", "dispatch-main", "dispatch-feature", "pull-request"],
)
def test_coverage_publisher_event_and_ref_matrix(
    workflow: str,
    job_name: str,
    event_context: tuple[str, str],
    expected_policy: str,
) -> None:
    """Only eligible main events may publish the measured PR baseline."""
    event, reference = event_context
    definition, job, action = _coverage_job(workflow, job_name)
    triggers = definition.get("on", definition.get(True))
    is_main_guard_satisfied = job.get("if") is None or reference == "refs/heads/main"
    does_action_publish = action["with"].get("publish-baseline") == "always"
    is_publisher = event in triggers and is_main_guard_satisfied and does_action_publish
    actual_policy = "publish" if is_publisher else "skip"
    assert actual_policy == expected_policy, (
        f"{workflow} must honour the {event} event at {reference} publisher policy."
    )
