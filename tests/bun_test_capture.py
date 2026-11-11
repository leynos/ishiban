"""Capture bounded Bun test output for cross-runtime contract tests."""

import asyncio
import os
import pathlib

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_CAPTURE_BYTES = 1024 * 1024


async def capture_bun_test_output(
    directory: pathlib.Path, *, test_file: str, variable: str
) -> bytes:
    """Run one Bun test and return its captured output.

    For example, the recency and inspector contracts pass the browser's own
    request bytes to Falcon rather than recreating the URL or JSON in Python.

    Returns
    -------
    bytes
        The Bun test's private capture file contents.

    """
    capture = directory / f"{variable.lower()}.json"
    environment = {**os.environ, variable: str(capture)}
    await _run_bun_test(test_file, environment)
    return _read_capture(capture)


async def _run_bun_test(test_file: str, environment: dict[str, str]) -> None:
    """Run one Bun test with bounded merged output and process lifetime.

    For example, a flooding test is killed and reaped before it can fill memory.

    Raises
    ------
    AssertionError
        If Bun fails or prints more than 1 MiB.
    """
    process = await asyncio.create_subprocess_exec(
        "bun",
        "test",
        test_file,
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        async with asyncio.timeout(20):
            output = await _read_bun_stdout(process.stdout)
            await process.wait()
        if process.returncode != 0:
            raise AssertionError(output.decode(errors="replace"))
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _read_bun_stdout(stdout: asyncio.StreamReader | None) -> bytes:
    """Collect merged Bun output up to the first byte beyond its bound.

    For example, a child that prints 1 MiB plus one byte is rejected promptly.

    Returns
    -------
    bytes
        At most 1 MiB of diagnostic output.

    Raises
    ------
    AssertionError
        If the stream is absent or exceeds the configured byte limit.
    """
    if stdout is None:
        message = "stdout missing"
        raise AssertionError(message)
    try:
        output = await stdout.readexactly(MAX_CAPTURE_BYTES + 1)
    except asyncio.IncompleteReadError as exc:
        output = exc.partial
    if len(output) > MAX_CAPTURE_BYTES:
        message = "stdout > 1 MiB"
        raise AssertionError(message)
    return output


def _read_capture(capture: pathlib.Path) -> bytes:
    """Read one bounded completed capture without trusting its stat alone.

    For example, a test writing more than 1 MiB is rejected before reading.

    Returns
    -------
    bytes
        At most 1 MiB of captured test output.

    Raises
    ------
    AssertionError
        If the captured file exceeds the configured byte limit.
    """
    if capture.stat().st_size > MAX_CAPTURE_BYTES:
        message = "capture > 1 MiB"
        raise AssertionError(message)
    with capture.open("rb") as captured:
        content = captured.read(MAX_CAPTURE_BYTES + 1)
    if len(content) > MAX_CAPTURE_BYTES:
        message = "capture > 1 MiB"
        raise AssertionError(message)
    return content
