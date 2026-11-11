"""Real subprocess boundary tests use a deterministic read-only fake Lody."""

import asyncio
import contextlib as ctx
import signal
import time
import types
import typing as typ

import msgspec
import pytest
from lody_process_support import create_fake_lody, tracked_fake_lody_children

from ishiban import lody
from ishiban.lody import read_catalogue

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.protocol import Catalogue


@ctx.asynccontextmanager
async def _tracked_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> cabc.AsyncIterator[list[lody._OwnedChild]]:
    """Capture the real adapter and force cleanup after a failing probe.

    Yields
    ------
    list of _OwnedChild
        Native owners created by the test's catalogue call.
    """
    owners: list[lody._OwnedChild] = []

    def tracked_child(command: tuple[str, ...]) -> lody._OwnedChild:
        """Record one native owner while preserving actual process execution.

        Returns
        -------
        _OwnedChild
            The adapter that will spawn and reap the fake executable.
        """
        owner = lody._OwnedChild(command)
        owners.append(owner)
        return owner

    with monkeypatch.context() as patch:
        patch.setattr(lody, "child", tracked_child)
        try:
            yield owners
        finally:
            for owner in owners:
                await _force_reap(owner)


async def _force_reap(owner: lody._OwnedChild) -> None:
    """Bound private test cleanup after a deliberately failing teardown probe.

    For example, a red test still kills and drains its fake child.
    """
    process = owner.process
    if process.returncode is None:
        process.kill()
    async with asyncio.timeout(3):
        if process.stdout is not None:
            while await process.stdout.read(65_536):
                pass
        await process.wait()
    if not owner.drainer.done():
        owner.drainer.cancel()
        with ctx.suppress(asyncio.CancelledError):
            await owner.drainer


async def _assert_killed_owner(owner: lody._OwnedChild) -> None:
    """Check SIGKILL, completed wait, and drained stderr for one fake child.

    For example, a TERM-resistant read must finish before the caller unwinds.
    """
    assert owner.process.returncode == -signal.SIGKILL, (
        "A TERM-resistant child must be killed before its owner unwinds."
    )
    assert await asyncio.wait_for(owner.process.wait(), timeout=1) == -signal.SIGKILL, (
        "The killed child must complete its wait before returning."
    )
    assert owner.drainer.done(), "The owned stderr drainer must be reaped."


def _wait_for_native_state(
    is_ready: cabc.Callable[[], bool], failure_message: str
) -> None:
    """Bound polling for native child evidence that has no asyncio notifier.

    For example, a fake child's TERM marker becomes visible to the test thread.
    """
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if is_ready():
            return
        time.sleep(0.01)
    pytest.fail(failure_message)


def _term_resistant_executable(
    directory: pathlib.Path, marker: pathlib.Path | None = None
) -> pathlib.Path:
    """Write a child that emits JSON, then fills stdout after ignoring TERM.

    Returns
    -------
    pathlib.Path
        A fake executable that lingers after ten megabytes of extra output.
    """
    payload = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [],
    }).decode()
    mark_term = f"    pathlib.Path({str(marker)!r}).touch()\n" if marker else ""
    executable, _ = create_fake_lody(
        directory,
        "import signal\n"
        "saw_term = False\n"
        "def note_term(_signal, _frame):\n"
        "    global saw_term\n"
        f"{mark_term}"
        "    saw_term = True\n"
        "signal.signal(signal.SIGTERM, note_term)\n"
        f"sys.stdout.write({payload!r})\n"
        "sys.stdout.flush()\n"
        "while not saw_term:\n"
        "    time.sleep(0.01)\n"
        "payload = 'x' * 10_000_000",
        linger_after_output=120,
    )
    return executable


@pytest.mark.parametrize(
    ("is_term_ignored", "expected_signal"),
    [(False, signal.SIGTERM), (True, signal.SIGKILL)],
    ids=["graceful-sigterm", "term-resistant-sigkill"],
)
@pytest.mark.asyncio
async def test_catalogue_reader_stops_after_complete_json(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_term_ignored: bool,
    expected_signal: signal.Signals,
) -> None:
    """A complete snapshot closes and reaps even a TERM-resistant child."""
    payload = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [],
    }).decode()
    ignore_term = (
        "import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        if is_term_ignored
        else ""
    )
    executable, _ = create_fake_lody(
        tmp_path,
        f"{ignore_term}payload = {payload!r}",
        linger_after_output=120,
    )
    async with tracked_fake_lody_children(monkeypatch, executable) as children:
        catalogue = await asyncio.wait_for(
            read_catalogue("leynos", str(executable)), timeout=9
        )
        assert catalogue.workspace_id == "workspace", (
            "A complete response must preserve the configured workspace identity."
        )
        assert catalogue.sessions == [], (
            "An explicit empty list must return despite the lingering transport."
        )
        assert len(children) == 1, "The catalogue read must own one native child."
        child = children[0][1]
        assert child.returncode == -expected_signal, (
            f"The completed read must terminate its child with {expected_signal.name}."
        )
        assert await asyncio.wait_for(child.wait(), timeout=1) == -expected_signal, (
            f"The {expected_signal.name} child must be reaped before returning."
        )


@pytest.mark.asyncio
async def test_term_resistant_child_with_full_stdout_is_reaped_after_early_json(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked stdout pipe cannot stall cleanup after a complete catalogue."""
    executable = _term_resistant_executable(tmp_path)
    async with _tracked_owner(monkeypatch) as owners:
        catalogue = await asyncio.wait_for(
            read_catalogue("leynos", str(executable)), timeout=7
        )
        assert catalogue.workspace_id == "workspace", (
            "The complete JSON must be accepted before excess output fills the pipe."
        )
        assert len(owners) == 1, "One catalogue lookup must own one native child."
        await _assert_killed_owner(owners[0])


@pytest.mark.asyncio
async def test_cancelling_termination_still_reaps_term_resistant_child(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation during the grace period must finish owned child cleanup."""
    marker = tmp_path / "term-received"
    executable = _term_resistant_executable(tmp_path, marker)
    async with _tracked_owner(monkeypatch) as owners:
        task = asyncio.create_task(read_catalogue("leynos", str(executable)))
        try:
            await asyncio.to_thread(
                _wait_for_native_state,
                marker.exists,
                "The fake child did not acknowledge SIGTERM.",
            )
            assert task.cancel(), "The live catalogue read must accept cancellation."
            await asyncio.sleep(0)
            assert task.cancel(), (
                "Repeated cancellation must not abandon child cleanup."
            )
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=7)
            assert len(owners) == 1, "Cancellation must target one native child."
            await _assert_killed_owner(owners[0])
        finally:
            if not task.done():
                task.cancel()
                with ctx.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=7)


@pytest.mark.asyncio
async def test_already_exited_child_still_drains_full_stdout(
    tmp_path: pathlib.Path,
) -> None:
    """An observed exit code does not excuse unread stdout transport cleanup."""
    executable, _ = create_fake_lody(tmp_path, "payload = 'x' * 10_000_000")
    owner = lody.child((str(executable),))

    async def exit_with_full_pipe() -> None:
        """Kill only the fake child after its output has begun filling the pipe."""
        async with owner as process:
            assert process.stdout is not None, "The native child must expose stdout."
            assert await asyncio.wait_for(process.stdout.read(1), timeout=1) == b"x", (
                "The child must begin writing before the parent kills it."
            )
            await asyncio.sleep(0.1)
            process.kill()
            await asyncio.to_thread(
                _wait_for_native_state,
                lambda: process.returncode is not None,
                "The killed fake child did not report an exit code.",
            )
            assert process.returncode == -signal.SIGKILL, (
                "The process must have exited before its owner cleans the pipe."
            )

    await asyncio.wait_for(exit_with_full_pipe(), timeout=4)
    assert owner.process.stdout is not None, "The native stdout reader must exist."
    assert owner.process.stdout.at_eof(), (
        "An already-exited child must still drain buffered stdout to EOF."
    )
    assert owner.drainer.done(), "The stderr drainer must finish on this path."


@pytest.mark.asyncio
async def test_chunked_catalogue_is_decoded_once_when_its_root_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport chunk count must not multiply full-buffer JSON decoding work."""
    payload = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [{"id": "session", "title": 'Nested {braces} and "quotes"'}],
    })
    chunks = [payload[offset : offset + 5] for offset in range(0, len(payload), 5)]
    decoded_lengths: list[int] = []
    original_decoder = lody.decode_catalogue

    @ctx.asynccontextmanager
    async def chunked_child(
        _command: tuple[str, ...],
    ) -> cabc.AsyncIterator[types.SimpleNamespace]:
        """Supply pipe chunks without replacing the actual protocol decoder.

        Yields
        ------
        types.SimpleNamespace
            A process boundary exposing its chunked stdout pipe.
        """
        pipe = asyncio.StreamReader()

        async def deliver_chunks() -> None:
            """Deliver partial pipe reads before publishing the EOF marker."""
            for chunk in chunks:
                pipe.feed_data(chunk)
                # Model separate transport deliveries, rather than a prefilled pipe.
                await asyncio.sleep(0)
            pipe.feed_eof()

        delivery = asyncio.create_task(deliver_chunks())
        try:
            yield types.SimpleNamespace(stdout=pipe, stdin=None)
        finally:
            await delivery

    def counted_decoder(data: bytes) -> Catalogue:
        """Count full-document work while exercising the real typed decoder.

        Returns
        -------
        Catalogue
            The catalogue produced by the original typed decoder.
        """
        decoded_lengths.append(len(data))
        return original_decoder(data)

    monkeypatch.setattr(lody, "child", chunked_child)
    monkeypatch.setattr(lody, "decode_catalogue", counted_decoder)
    catalogue = await lody.read_catalogue("leynos")
    assert catalogue.sessions[0].id == "session", (
        "Chunking and quoted structural characters must preserve catalogue facts."
    )
    assert decoded_lengths == [len(payload)], (
        "A complete catalogue must be decoded once, independent of pipe chunk count."
    )
