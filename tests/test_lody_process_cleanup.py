"""Cancellation and cleanup errors retain their original ownership order."""

import asyncio
import typing as typ
from unittest import mock

import pytest
from lody_process_support import create_fake_lody

from ishiban import lody, lody_process_cleanup

if typ.TYPE_CHECKING:
    import pathlib


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


@pytest.mark.asyncio
async def test_context_preserves_read_cancellation_when_cleanup_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An observer read cancelled before exit keeps cancellation as the outcome."""
    executable, _ = create_fake_lody(tmp_path, "payload = ''", linger_after_output=120)
    owner = lody.child((str(executable),))
    reading = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_finished = asyncio.Event()
    release_cleanup = asyncio.Event()
    failure = TimeoutError("owned cleanup expired")

    async def failed_cleanup(
        _process: asyncio.subprocess.Process, _stderr_drainer: asyncio.Task[None]
    ) -> None:
        """Fail only after the context has entered its real cleanup boundary."""
        cleanup_started.set()
        await release_cleanup.wait()
        cleanup_finished.set()
        raise failure

    async def blocked_observer_read() -> None:
        """Own a native child until cancellation interrupts its stdout read."""
        async with owner as process:
            assert process.stdout is not None, "The native child must expose stdout."
            reading.set()
            await process.stdout.read(1)

    real_cleanup = lody_process_cleanup._finish_child
    monkeypatch.setattr(lody_process_cleanup, "_finish_child", failed_cleanup)
    caller = asyncio.create_task(blocked_observer_read())
    try:
        await asyncio.wait_for(reading.wait(), timeout=1)
        assert caller.cancel("observer read stopped"), (
            "The blocked observer read must accept cancellation."
        )
        await asyncio.wait_for(cleanup_started.wait(), timeout=1)
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(caller, timeout=1)
        assert cleanup_finished.is_set(), "Owned cleanup must finish before unwind."
        assert raised.value.args == ("observer read stopped",), (
            "The original read cancellation payload must survive cleanup."
        )
        assert raised.value.__cause__ is failure, (
            "Cleanup failure must be retained as the read cancellation's cause."
        )
    finally:
        release_cleanup.set()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
        await real_cleanup(owner.process, owner.drainer)
