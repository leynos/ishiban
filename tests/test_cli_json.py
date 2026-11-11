"""Recognize bounded JSON around Lody's documented transport chatter only."""

import json
import sys
import typing as typ

import pytest

from ishiban.lody import read_json_object
from ishiban.protocol import ProtocolError

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_configuration_transport_lines_do_not_hide_its_json(
    tmp_path: Path,
) -> None:
    """A complete object is available even while the transport lingers."""
    executable = tmp_path / "lody"
    body = {"ok": True, "agentConfig": {"id": "c1", "name": "Codex"}}
    output = "[workspace-1] Remote Streams transport attached\n" + json.dumps(body)
    output += "\n[workspace-1] Remote Streams transport detached\n"
    executable.write_text(
        f"#!{sys.executable}\nimport sys,time\n"
        f"sys.stdout.write({output!r});sys.stdout.flush()\ntime.sleep(5)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    actual = await read_json_object(
        (str(executable),), allow_transport_logs=True, deadline_seconds=1
    )
    assert json.loads(actual) == body, (
        "Only the actual configuration object may be decoded."
    )


@pytest.mark.asyncio
async def test_unrecognized_stdout_is_not_treated_as_transport_chatter(
    tmp_path: Path,
) -> None:
    """Unknown text cannot be silently discarded before an apparent JSON response."""
    executable = tmp_path / "lody"
    executable.write_text(
        f"#!{sys.executable}\nprint('unexpected output')\nprint('{{}}')\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    with pytest.raises(ProtocolError, match="Unexpected CLI output"):
        await read_json_object((str(executable),), allow_transport_logs=True)
