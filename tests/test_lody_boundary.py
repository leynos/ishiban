"""Real subprocess boundary tests use a deterministic read-only fake Lody."""

import asyncio
import sys
import typing as typ

import msgspec
import pytest

from ishiban.lody import read_catalogue

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.asyncio
async def test_catalogue_reader_stops_after_complete_json(
    tmp_path: pathlib.Path,
) -> None:
    """A lingering transport must not hold an already complete snapshot hostage."""
    executable = tmp_path / "fake-lody"
    payload = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [],
    }).decode()
    executable.write_text(
        f"#!{sys.executable}\nimport time\n"
        f"print({payload!r}, flush=True)\ntime.sleep(120)\n"
    )
    executable.chmod(0o700)
    catalogue = await asyncio.wait_for(
        read_catalogue("leynos", str(executable)), timeout=10
    )
    assert catalogue.workspace_id == "workspace", (
        "A complete response must preserve the configured workspace identity."
    )
    assert catalogue.sessions == [], (
        "An explicit empty list must be accepted without waiting for child teardown."
    )
