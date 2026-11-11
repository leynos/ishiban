"""Reap test children whose stderr was merged into their stdout pipe."""

import asyncio

from ishiban.lody_process_cleanup import reap_child


async def reap_merged_output_child(
    process: asyncio.subprocess.Process,
    *,
    cancellation: asyncio.CancelledError | None = None,
) -> None:
    """Drain and reap a child after its bounded stdout reader has stopped.

    For example, a child blocked writing excess diagnostics is terminated
    while stdout is discarded in chunks, so its pipe cannot stall ``wait``.

    Parameters
    ----------
    process : asyncio.subprocess.Process
        The command runner's owned child.
    cancellation : asyncio.CancelledError or None, optional
        An incoming cancellation to preserve through bounded teardown.
    """
    # The production cleanup owns the same pipe contract. Merged stderr has
    # no separate reader task, so provide its already-completing counterpart.
    absent_stderr_drainer = asyncio.create_task(asyncio.sleep(0))
    await reap_child(process, absent_stderr_drainer, cancellation=cancellation)
