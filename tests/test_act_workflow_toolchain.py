"""Contract checks for the Act validation workflow's toolchain."""

import json
from pathlib import Path

import yaml


def test_act_validation_provisions_project_bun_before_running_tests() -> None:
    """Keep Act validation aligned with the repository's declared Bun version."""
    repository = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (repository / ".github/workflows/act-validation.yml").read_text(
            encoding="utf-8"
        )
    )
    package = json.loads((repository / "package.json").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["act-validation"]["steps"]
    bun_setup_step = next(
        (
            step
            for step in steps
            if step.get("uses", "").startswith("oven-sh/setup-bun@")
        ),
        None,
    )
    act_test_step = next(
        step for step in steps if step["name"] == "Run tests with act validation"
    )
    declared_bun_version = package["packageManager"].removeprefix("bun@")

    assert bun_setup_step is not None, "Act validation must install Bun before tests"
    assert steps.index(bun_setup_step) < steps.index(act_test_step), (
        "Act validation must install Bun before running tests"
    )
    assert bun_setup_step["with"]["bun-version"] == declared_bun_version, (
        "Act validation must use the Bun version declared by package.json"
    )
