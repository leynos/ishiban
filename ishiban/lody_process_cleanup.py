"""Bound native CLI child teardown without retaining pipe output.

For example, a child that ignores SIGTERM and fills stdout is killed, drained,
and reaped before its cancelled caller unwinds.
"""

import asyncio
import contextlib


async def discard_pipe(pipe: asyncio.StreamReader | None) -> None:
    """Read bounded chunks and discard them without keeping private output.

    For example, an unread stdout pipe cannot stall a killed child's wait.

    Parameters
    ----------
    pipe : asyncio.StreamReader or None
        The owned native child's pipe, or None when it has no such stream.
    """
    if pipe is not None:
        while await pipe.read(8192):
            pass


async def _stop_drainer(drainer: asyncio.Task[None]) -> None:
    """Cancel and reap a pipe drainer after its child has stopped.

    For example, a stopped child leaves no stderr reader task behind.
    """
    drainer.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await drainer


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Give a child three seconds to exit, then kill and reap within three more.

    For example, a TERM-resistant child with full stdout receives SIGKILL.
    """
    # A filled stdout pipe can block wait even after SIGKILL; drain after reads stop.
    stdout_drainer = asyncio.create_task(discard_pipe(process.stdout))
    try:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            async with asyncio.timeout(3):
                await process.wait()
                await asyncio.shield(stdout_drainer)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            async with asyncio.timeout(3):
                await process.wait()
                await asyncio.shield(stdout_drainer)
    finally:
        await _stop_drainer(stdout_drainer)


async def _finish_child(
    process: asyncio.subprocess.Process, stderr_drainer: asyncio.Task[None]
) -> None:
    """Reap both the process and its stderr reader even if termination fails.

    For example, a timed-out child still releases its stderr consumer.
    """
    try:
        async with asyncio.timeout(7):
            await _terminate(process)
    finally:
        await _stop_drainer(stderr_drainer)


async def reap_child(
    process: asyncio.subprocess.Process,
    stderr_drainer: asyncio.Task[None],
    *,
    cancellation: asyncio.CancelledError | None = None,
) -> None:
    """Complete bounded teardown despite caller cancellation, then propagate it.

    For example, cancellation during a TERM-resistant child's grace period
    waits for SIGKILL and pipe cleanup before raising ``CancelledError``.
    A cleanup ``TimeoutError`` propagates on its own or becomes the cause of
    caller cancellation.

    Parameters
    ----------
    process : asyncio.subprocess.Process
        The owned child after the caller has stopped reading stdout.
    stderr_drainer : asyncio.Task of None
        The child's existing stderr consumer, transferred to teardown ownership.
    cancellation : asyncio.CancelledError, optional
        Cancellation already raised by the context body before teardown starts.

    Raises
    ------
    asyncio.CancelledError
        The caller was cancelled. A simultaneous cleanup failure is its cause.
    """
    cleanup = asyncio.create_task(_finish_child(process, stderr_drainer))
    was_cancelled = False
    # asyncio.wait observes completion without transferring caller cancellation
    # or the cleanup exception; the owned task has its own seven-second bound.
    while not cleanup.done():
        try:
            await asyncio.wait({cleanup})
        except asyncio.CancelledError:
            was_cancelled = True
    if cancellation is not None:
        raise cancellation from cleanup.exception()
    if was_cancelled:
        raise asyncio.CancelledError from cleanup.exception()
    await cleanup
