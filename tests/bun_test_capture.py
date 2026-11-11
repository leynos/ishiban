"""Capture bounded Bun test output for cross-runtime contract tests."""

import asyncio
import os
import pathlib

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_CAPTURE_BYTES = 1024 * 1024


class _CapturePipe:
    """Drain a private FIFO as Bun writes, retaining at most one excess byte."""

    def __init__(self, path: pathlib.Path) -> None:
        """Open both FIFO ends so a Bun writer can connect without blocking."""
        os.mkfifo(path, 0o600)
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.loop = asyncio.get_running_loop()
        self.overflow: asyncio.Future[None] = self.loop.create_future()
        self.content = bytearray()
        self.loop.add_reader(self.fd, self._drain)

    def _drain(self) -> None:
        """Consume pending bytes; for example, signal at the first excess byte."""
        while True:
            remaining = MAX_CAPTURE_BYTES + 1 - len(self.content)
            try:
                chunk = os.read(self.fd, min(65536, remaining))
            except BlockingIOError:
                return
            if not chunk:
                return
            self.content.extend(chunk)
            if len(self.content) > MAX_CAPTURE_BYTES:
                self.loop.remove_reader(self.fd)
                self.overflow.set_result(None)
                return

    def finish(self) -> bytes:
        """Return bounded bytes after Bun exits, including the final pipe buffer.

        For example, a short JSON body remains byte-for-byte unchanged.

        Returns
        -------
        bytes
            The complete captured payload within the one MiB limit.

        Raises
        ------
        AssertionError
            If the captured payload exceeded the limit.
        """
        if not self.overflow.done():
            self._drain()
        if self.overflow.done():
            message = "capture > 1 MiB"
            raise AssertionError(message)
        return bytes(self.content)

    def close(self) -> None:
        """Release the reader and remove its private FIFO after the child exits."""
        self.loop.remove_reader(self.fd)
        os.close(self.fd)
        self.path.unlink()


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
    pipe = _CapturePipe(capture)
    try:
        environment = {**os.environ, variable: str(capture)}
        return await _run_bun_test(test_file, environment, pipe)
    finally:
        pipe.close()


async def _run_bun_test(
    test_file: str, environment: dict[str, str], capture: _CapturePipe
) -> bytes:
    """Run one Bun test with bounded merged output and process lifetime.

    For example, a flooding test is killed and reaped before it can fill memory.

    Returns
    -------
    bytes
        The complete FIFO payload after the Bun child exits successfully.

    Raises
    ------
    AssertionError
        If Bun fails or either channel exceeds one MiB.
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
            completion = asyncio.gather(
                _read_bun_stdout(process.stdout), process.wait()
            )
            try:
                done, _pending = await asyncio.wait(
                    {completion, capture.overflow}, return_when=asyncio.FIRST_COMPLETED
                )
                if capture.overflow in done:
                    message = "capture > 1 MiB"
                    raise AssertionError(message)
                output, _status = completion.result()
                captured = capture.finish()
            finally:
                completion.cancel()
                await asyncio.gather(completion, return_exceptions=True)
        if process.returncode != 0:
            raise AssertionError(output.decode(errors="replace"))
        return captured
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
