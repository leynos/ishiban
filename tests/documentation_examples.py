"""Load executable examples from the published Ishiban users' guide."""

import pathlib
import re
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

USER_GUIDE = pathlib.Path(__file__).resolve().parents[1] / "docs/users-guide.md"
MARKER = re.compile(r"<!-- tested-example: ([a-z][a-z0-9-]*) -->")


def _fenced_source(
    numbered_lines: cabc.Iterator[tuple[int, str]], identifier: str
) -> str:
    """Consume one Bash fence after its marker, preserving its published lines.

    For example, a missing closing fence raises instead of yielding a partial
    command that a test might accidentally treat as complete.

    Returns
    -------
    str
        The exact command lines without Markdown delimiters.

    Raises
    ------
    ValueError
        If the fence has no closing delimiter.
    """
    source: list[str] = []
    for _number, line in numbered_lines:
        if line == "```":
            return "\n".join(source)
        source.append(line)
    message = f"Unterminated fence for example {identifier}."
    raise ValueError(message)


def _marked_example(
    numbered_lines: cabc.Iterator[tuple[int, str]],
    number: int,
    marker_line: str,
    existing: dict[str, str],
) -> tuple[str, str]:
    """Validate one marker and consume its immediately following Bash fence.

    For example, duplicate ``setup`` IDs fail before any later command runs.

    Returns
    -------
    tuple[str, str]
        Stable example ID and its complete published source.

    Raises
    ------
    ValueError
        If the marker is malformed, duplicated, or detached from its fence.
    """
    marker = MARKER.fullmatch(marker_line)
    if marker is None:
        message = f"Missing or malformed tested-example ID at line {number}."
        raise ValueError(message)
    identifier = marker.group(1)
    if identifier in existing:
        message = f"Duplicate tested-example ID {identifier}."
        raise ValueError(message)
    opening = next(numbered_lines, None)
    if opening is None or opening[1] != "```bash":
        message = f"Example {identifier} marker must precede its Bash fence."
        raise ValueError(message)
    return identifier, _fenced_source(numbered_lines, identifier)


def load_user_guide_examples(path: pathlib.Path = USER_GUIDE) -> dict[str, str]:
    """Return marked Bash examples and reject uncovered or malformed fences.

    For example, ``load_user_guide_examples()["collect"]`` returns the exact
    command printed in the installed users' guide.

    Returns
    -------
    dict[str, str]
        Stable marker IDs mapped to their published Bash source.

    Raises
    ------
    ValueError
        If a marker or fence violates the tested-example contract.
    """
    examples: dict[str, str] = {}
    numbered_lines = iter(enumerate(path.read_text(encoding="utf-8").splitlines(), 1))
    for number, line in numbered_lines:
        if line.startswith("<!-- tested-example:"):
            identifier, source = _marked_example(numbered_lines, number, line, examples)
            examples[identifier] = source
            continue
        if line.lstrip().startswith(("```", "~~~")):
            message = f"Unmarked fence at line {number}."
            raise ValueError(message)
    return examples
