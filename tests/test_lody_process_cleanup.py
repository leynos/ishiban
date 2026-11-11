"""Cancellation and cleanup errors retain their original ownership order."""

import asyncio
from unittest import mock

import pytest

from ishiban import lody_process_cleanup


@pytest.mark.parametrize(
    ("cancel_caller", "expected_error"),
    [
        (False, TimeoutError),
        (True, asyncio.CancelledError),
    ],
    ids=["cleanup-error", "caller-cancelled-with-cleanup-cause"],
)
@pytest.mark.asyncio
async def test_reap_child_observes_cleanup_before_unwinding(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cancel_caller: bool,
    expected_error: type[BaseException],
) -> None:
    """A cancelled caller gets its cancellation with the cleanup error as cause."""
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    failure = TimeoutError("owned cleanup expired")

    async def failed_cleanup(
        _process: asyncio.subprocess.Process, _stderr_drainer: asyncio.Task[None]
    ) -> None:
        """Expose the join boundary while leaving the real child adapter untouched."""
        started.set()
        await release.wait()
        finished.set()
        raise failure

    monkeypatch.setattr(lody_process_cleanup, "_finish_child", failed_cleanup)
    stderr_drainer = asyncio.create_task(asyncio.sleep(0))
    process = mock.Mock(spec=asyncio.subprocess.Process)
    caller = asyncio.create_task(
        lody_process_cleanup.reap_child(process, stderr_drainer)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        if cancel_caller:
            assert caller.cancel(), "The pending join must accept caller cancellation."
            await asyncio.sleep(0)
        release.set()
        with pytest.raises(expected_error) as raised:
            await asyncio.wait_for(caller, timeout=1)
        assert finished.is_set(), "Cleanup must finish before the caller unwinds."
        if cancel_caller:
            assert raised.value.__cause__ is failure, (
                "The cleanup failure must remain attached to caller cancellation."
            )
        else:
            assert raised.value is failure, (
                "Without caller cancellation, preserve the cleanup exception."
            )
    finally:
        release.set()
        await asyncio.wait_for(
            asyncio.gather(caller, stderr_drainer, return_exceptions=True), timeout=1
        )
