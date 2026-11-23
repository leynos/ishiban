"""Register verified command doubles for tests that need ordinary CLI responses."""

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import pathlib

pytest_plugins = ("cmd_mox.pytest_plugin",)


@pytest.fixture(autouse=True)
def isolated_xdg_state_home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    """Keep every default CLI state directory inside this test's temporary tree.

    Returns
    -------
    pathlib.Path
        The XDG state root that default-state resolution must use.
    """
    state_home = tmp_path / "xdg-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    return state_home
