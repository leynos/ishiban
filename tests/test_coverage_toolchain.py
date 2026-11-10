"""PR and main coverage share a measured, migration-aware toolchain."""

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("workflow", "job"),
    [("ci.yml", "lint-test"), ("coverage-main.yml", "coverage-upload")],
    ids=["pull-request", "main-publisher"],
)
def test_coverage_lanes_share_instrumentation_contract(workflow: str, job: str) -> None:
    """Compatible serial instrumentation retains the existing ratchet and scope."""
    definition = yaml.safe_load(
        (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    )
    step = next(
        item
        for item in definition["jobs"][job]["steps"]
        if item.get("uses", "").startswith(
            "leynos/shared-actions/.github/actions/generate-coverage@"
        )
    )
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
