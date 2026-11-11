"""Exercise published setup and Act commands at safe process boundaries."""

import asyncio
import pathlib
import shlex
import shutil
import sys
import time
import typing as typ

import pytest
from cmd_mox import Invocation, Response
from documentation_examples import load_user_guide_examples
from merged_output_process import reap_merged_output_child

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


async def _bounded_command_output(stdout: asyncio.StreamReader | None) -> bytes:
    """Read one test command's diagnostics without unbounded pipe growth.

    For example, the Make dry-run remains below 8 KiB while exposing its
    pytest environment assignment.

    Returns
    -------
    bytes
        At most 8 KiB of command output.

    Raises
    ------
    AssertionError
        If the stream is absent or prints beyond its byte limit.
    """
    if stdout is None:
        message = "Guide command output stream missing."
        raise AssertionError(message)
    try:
        output = await stdout.readexactly(8193)
    except asyncio.IncompleteReadError as exc:
        output = exc.partial
    if len(output) > 8192:
        message = "Guide command output exceeded 8 KiB."
        raise AssertionError(message)
    return output


async def _run_example(argv: list[str], cwd: pathlib.Path) -> str:
    """Run only whitelisted guide argv with bounded output and lifetime.

    For example, the real Make dry-run can expose its pytest environment
    without running test or Act recipes.

    Returns
    -------
    str
        At most 8 KiB of command output for assertions.

    Raises
    ------
    AssertionError
        If the command fails or exceeds its diagnostic output bound.
    asyncio.CancelledError
        If the caller cancels the command; the child is reaped first.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    cancellation: asyncio.CancelledError | None = None
    try:
        async with asyncio.timeout(5):
            output = await _bounded_command_output(process.stdout)
            await process.wait()
        if process.returncode != 0:
            raise AssertionError(output.decode(errors="replace"))
        return output.decode(errors="replace")
    except asyncio.CancelledError as exc:
        cancellation = exc
        raise
    finally:
        await reap_merged_output_child(process, cancellation=cancellation)


@pytest.mark.asyncio
async def test_guide_command_overflow_reaps_child_with_full_pipe(
    tmp_path: pathlib.Path,
) -> None:
    """Excess diagnostics cannot strand a guide command's killed child."""
    script = tmp_path / "flood.py"
    script.write_text(
        "import os\nimport time\nos.write(1, b'x' * 1048576)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    with pytest.raises(AssertionError, match="exceeded 8 KiB"):
        await asyncio.wait_for(
            _run_example([sys.executable, str(script)], tmp_path), timeout=9
        )
    assert time.monotonic() - started < 5, (
        "A guide command's excess output must stop promptly after bounded cleanup."
    )


@pytest.mark.asyncio
async def test_setup_commands_use_mocked_external_tools(
    tmp_path: pathlib.Path, cmd_mox: CmdMox
) -> None:
    """The three published setup lines reach their exact uv and Bun shims."""
    examples = load_user_guide_examples()
    commands = [shlex.split(line) for line in examples["setup"].splitlines()]
    assert len(commands) == 3, "The published setup must contain three commands."
    assert all(argv[0] in {"uv", "bun"} for argv in commands), (
        "Only mocked setup executables may be dispatched."
    )
    cmd_mox.mock("uv").with_args("sync", "--group", "dev").returns()

    def record_bun(_invocation: Invocation) -> Response:
        """Acknowledge only the shim, never an installation or browser build.

        Returns
        -------
        Response
            Empty successful output for the published Bun commands.
        """
        return Response()

    bun = cmd_mox.spy("bun").runs(record_bun)
    for argv in commands:
        assert not await _run_example(argv, tmp_path), (
            "The mocked setup command must pass without performing an install."
        )
    assert [invocation.args for invocation in bun.invocations] == [
        ["install", "--frozen-lockfile"],
        ["run", "build"],
    ], "The published Bun setup must install locked dependencies and build."


@pytest.mark.asyncio
async def test_act_command_sets_pytest_environment_without_running_act(
    tmp_path: pathlib.Path, cmd_mox: CmdMox
) -> None:
    """The published make command expands to the opt-in pytest environment."""
    argv = shlex.split(load_user_guide_examples()["act-validation"])
    assert argv == ["make", "test", "WITH_ACT=1"], (
        "The documented opt-in must identify the existing Make target."
    )
    make = shutil.which("make")
    assert make is not None, "The local Makefile contract needs installed make."
    dry_run = await _run_example([make, "--dry-run", *argv[1:]], REPOSITORY_ROOT)
    pytest_lines = [line for line in dry_run.splitlines() if " run pytest -v " in line]
    assert len(pytest_lines) == 1, "Dry-run must expose one pytest invocation."
    assert "RUN_ACT_VALIDATION=1" in pytest_lines[0], (
        "WITH_ACT=1 must reach pytest as the opt-in environment variable."
    )

    cmd_mox.mock("make").with_args("test", "WITH_ACT=1").returns()
    assert not await _run_example(argv, tmp_path), (
        "The published make argv must reach the mock without running Act."
    )
