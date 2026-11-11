"""Shared plumbing for fake Lody subprocesses in reader tests."""

import asyncio
import contextlib
import pathlib
import sys
import typing as typ

from ishiban import lody

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest


def create_fake_lody(
    directory: pathlib.Path,
    response_code: str,
    *,
    linger_after_output: float = 0,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Write a fake CLI that logs arguments and emits the supplied response.

    Parameters
    ----------
    directory : pathlib.Path
        Directory that owns the executable and call log.
    response_code : str
        Python source that assigns the response text to ``payload``.
    linger_after_output : float, default 0
        Number of seconds the child remains alive after output is flushed.

    Returns
    -------
    tuple of pathlib.Path
        The executable path followed by the command invocation log path.
    """
    directory.mkdir(parents=True, exist_ok=True)
    call_log = pathlib.Path(directory, "calls.log")
    source = (
        f"#!{sys.executable}\n"
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        f"call_log = pathlib.Path({str(call_log)!r})\n"
        "args = sys.argv[1:]\n"
        "with call_log.open('a', encoding='utf-8') as log:\n"
        "    log.write('\\t'.join(args) + '\\n')\n"
        f"{response_code}\n"
        "sys.stdout.write(payload)\n"
        "sys.stdout.flush()\n"
        f"time.sleep({linger_after_output!r})\n"
    )
    executable = pathlib.Path(directory, "fake-lody")
    executable.write_text(source, encoding="utf-8")
    executable.chmod(0o700)
    return executable, call_log


@contextlib.asynccontextmanager
async def tracked_fake_lody_children(
    monkeypatch: pytest.MonkeyPatch,
    executable: pathlib.Path,
) -> cabc.AsyncIterator[list[tuple[tuple[str, ...], asyncio.subprocess.Process]]]:
    """Track real children of one fake CLI and reap any left by a failed test.

    For example, a catalogue read can assert its child's return code after
    the response is parsed. The wrapper still calls the native process adapter.

    Yields
    ------
    list of tuple of command and asyncio.subprocess.Process
        Commands and native handles for this executable only.
    """
    children: list[tuple[tuple[str, ...], asyncio.subprocess.Process]] = []
    original_enter = lody._OwnedChild.__aenter__

    async def tracked_enter(
        owner: lody._OwnedChild,
    ) -> asyncio.subprocess.Process:
        """Record the owned native process after the real adapter starts it.

        Returns
        -------
        asyncio.subprocess.Process
            The native process created by the original adapter.
        """
        process = await original_enter(owner)
        if owner.command[0] == str(executable):
            children.append((owner.command, process))
        return process

    with monkeypatch.context() as patch:
        patch.setattr(lody._OwnedChild, "__aenter__", tracked_enter)
        try:
            yield children
        finally:
            for _, process in children:
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                await asyncio.wait_for(process.wait(), timeout=3)


async def wait_for_calls(path: pathlib.Path, count: int = 1) -> list[str]:
    """Wait for the fake executable to record the requested command count.

    Returns
    -------
    list of str
        Recorded argument lines after at least ``count`` calls are present.

    Raises
    ------
    AssertionError
        If the expected command records do not appear within three seconds.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 3
    while loop.time() < deadline:
        lines = await asyncio.to_thread(_read_call_lines, path)
        if len(lines) >= count:
            return lines
        await asyncio.sleep(0.01)
    message = "The fake Lody executable did not record the expected commands."
    raise AssertionError(message)


def _read_call_lines(path: pathlib.Path) -> list[str]:
    """Read call records without blocking the event loop.

    Returns
    -------
    list of str
        Recorded command arguments, or an empty list before the first call.
    """
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()
