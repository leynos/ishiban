"""Keep every published users' guide command marked and parseable."""

import shlex
import typing as typ

import pytest
from documentation_examples import load_user_guide_examples

if typ.TYPE_CHECKING:
    import pathlib

DUPLICATE_MARKERS = (
    "<!-- tested-example: setup -->\n```bash\nuv sync\n```\n"
    "<!-- tested-example: setup -->\n```bash\nbun install\n```\n"
)


def test_published_guide_has_four_executable_examples() -> None:
    """The loader must inspect the actual guide rather than copied commands."""
    examples = load_user_guide_examples()
    assert set(examples) == {"setup", "collect", "serve", "act-validation"}, (
        "Every published fence needs one stable tested-example marker."
    )
    assert all(
        shlex.split(line)
        for example in examples.values()
        for line in example.splitlines()
    ), "The published Bash lines must parse into command arguments."


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        ("```bash\nuv sync\n```\n", "Unmarked fence"),
        ("<!-- tested-example: -->\n```bash\nuv sync\n```\n", "Missing or malformed"),
        ("<!-- tested-example: setup -->\n```bash\nuv sync\n", "Unterminated fence"),
        (DUPLICATE_MARKERS, "Duplicate tested-example"),
        ("<!-- tested-example: setup -->\n\n```bash\nuv sync\n```\n", "must precede"),
    ],
)
def test_loader_rejects_uncovered_or_malformed_examples(
    tmp_path: pathlib.Path, source: str, diagnostic: str
) -> None:
    """Invalid marker layouts fail before any example can be executed."""
    guide = tmp_path / "users-guide.md"
    guide.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match=diagnostic):
        load_user_guide_examples(guide)
