"""Resolve the shared default state directory from the XDG environment."""

import pathlib

import cyclopts
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ishiban import cli

COMMAND_CHAIN = ("collect",)


def _unavailable_home(_cls: type[pathlib.Path]) -> pathlib.Path:
    """Simulate a platform whose home directory cannot be determined.

    Raises
    ------
    RuntimeError
        Always, matching ``pathlib.Path.home()`` without a usable home.
    """
    message = "No home directory."
    raise RuntimeError(message)


def _remove_xdg_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the XDG state root genuinely unset for one scenario."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)


def _assert_unresolvable(isolated_xdg_state_home: pathlib.Path) -> None:
    """Assert the shared diagnostic and that no default state was created."""
    with pytest.raises(cyclopts.ValidationError) as rejected:
        cli.default_state_directory(command_chain=COMMAND_CHAIN)
    message = str(rejected.value)
    assert "XDG_STATE_HOME" in message, "The remedy must name the XDG variable."
    assert "--state-directory" in message, "The remedy must name the CLI override."
    assert not isolated_xdg_state_home.exists(), (
        "Resolution must not create the state root."
    )
    assert not (isolated_xdg_state_home / "ishiban").exists(), (
        "Resolution must not create the application state directory."
    )


def test_absolute_xdg_root_selects_the_shared_directory(
    isolated_xdg_state_home: pathlib.Path,
) -> None:
    """A valid absolute XDG root is used without resolving or creating it."""
    resolved = cli.default_state_directory(command_chain=COMMAND_CHAIN)

    assert resolved == isolated_xdg_state_home / "ishiban", (
        "A valid absolute XDG root must select its application directory."
    )
    assert resolved.is_absolute(), "The default must not depend on the cwd."
    assert not resolved.exists(), "Resolution must not create directories."


def test_unset_xdg_root_falls_back_to_local_state(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent XDG state root selects $HOME/.local/state."""
    _remove_xdg_root(monkeypatch)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    resolved = cli.default_state_directory(command_chain=COMMAND_CHAIN)

    assert resolved == home / ".local" / "state" / "ishiban", (
        "An absent XDG root must fall back to the home state directory."
    )
    assert not resolved.exists(), "Resolution must not create directories."


def _resolved_with_home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> tuple[pathlib.Path, pathlib.Path]:
    """Resolve the default under one configured XDG value and a private home.

    Returns
    -------
    tuple[pathlib.Path, pathlib.Path]
        The resolved default and the home directory that anchors the fallback.
    """
    monkeypatch.setenv("XDG_STATE_HOME", value)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    return cli.default_state_directory(command_chain=COMMAND_CHAIN), home


@pytest.mark.parametrize(
    "value", ["", "relative/state", "~/.state"], ids=["empty", "relative", "tilde"]
)
def test_invalid_xdg_root_is_ignored(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Empty and relative values are invalid under the XDG specification."""
    resolved, home = _resolved_with_home(tmp_path, monkeypatch, value)

    assert resolved == home / ".local" / "state" / "ishiban", (
        "An invalid XDG root must fall back to the home state directory."
    )
    assert "~" not in str(resolved), "No tilde expansion may occur."


def test_nonexistent_xdg_root_is_returned_without_creation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolution does not require the configured root to exist."""
    state_root = tmp_path / "missing" / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    resolved = cli.default_state_directory(command_chain=COMMAND_CHAIN)

    assert resolved == state_root / "ishiban", (
        "A missing XDG root must still be selected."
    )
    assert not state_root.exists(), "Resolution must not create the XDG root."


@pytest.mark.parametrize("value", ["", "relative"], ids=["empty", "relative"])
def test_unusable_home_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    isolated_xdg_state_home: pathlib.Path,
    value: str,
) -> None:
    """An empty or relative HOME cannot anchor the fallback state directory."""
    _remove_xdg_root(monkeypatch)
    monkeypatch.setenv("HOME", value)

    _assert_unresolvable(isolated_xdg_state_home)


def test_undeterminable_home_is_rejected(
    monkeypatch: pytest.MonkeyPatch, isolated_xdg_state_home: pathlib.Path
) -> None:
    """A platform without a home directory reports the same remedy."""
    _remove_xdg_root(monkeypatch)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(_unavailable_home))

    _assert_unresolvable(isolated_xdg_state_home)


@given(
    value=st.text(max_size=64).filter(
        lambda candidate: (
            "\x00" not in candidate and not pathlib.Path(candidate).is_absolute()
        )
    )
)
@settings(max_examples=50)
def test_every_resolved_default_is_absolute(value: str) -> None:
    """Invalid XDG values always fall back to the absolute per-user default."""
    home = pathlib.Path("/srv/ishiban-property-home")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("XDG_STATE_HOME", value)
        patch.setenv("HOME", str(home))
        resolved = cli.default_state_directory(command_chain=COMMAND_CHAIN)

    assert resolved == home / ".local" / "state" / "ishiban", (
        "Every invalid XDG value must select the home fallback."
    )
    assert resolved.is_absolute(), "The default must never be relative."


def test_resolver_does_not_expand_environment_variables(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured value is used literally, as the XDG specification requires."""
    state_root = tmp_path / "$ISHIBAN_STATE"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))
    monkeypatch.setenv("ISHIBAN_STATE", str(tmp_path / "expanded"))

    resolved = cli.default_state_directory(command_chain=COMMAND_CHAIN)

    assert resolved == state_root / "ishiban", (
        "A configured absolute XDG root must be used literally."
    )
    assert "expanded" not in str(resolved), "Variables must not be expanded."
