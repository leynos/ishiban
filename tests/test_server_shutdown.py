"""A real Falcon process must stop even while a browser holds an SSE stream."""

import asyncio
import signal
import socket
import sys
import typing as typ

import msgspec
import pytest

from ishiban.cli import WorkspaceConfig, database_url
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    import pathlib


def unused_port() -> int:
    """Reserve an ephemeral loopback port for this independent server test.

    Returns
    -------
    int
        The kernel-selected port after releasing the short reservation.
    """
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


async def connect_stream(
    port: int,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Wait for the actual server instead of sleeping for a guessed startup time.

    Returns
    -------
    tuple[asyncio.StreamReader, asyncio.StreamWriter]
        Connected loopback client streams.
    """
    async with asyncio.timeout(10):
        while True:
            try:
                return await asyncio.open_connection("127.0.0.1", port)
            except ConnectionRefusedError:
                await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_server_shutdown_is_bounded_with_an_open_event_stream(
    tmp_path: pathlib.Path,
) -> None:
    """Stopping the API must cancel a long-lived browser stream and exit."""
    store = Store(database_url(tmp_path), "workspace")
    await store.initialize()
    await store.begin_generation()
    await store.close()
    marker = WorkspaceConfig(workspace_id="workspace", selector="fixture")
    (tmp_path / "workspace.json").write_bytes(msgspec.json.encode(marker))
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text(
        "<!doctype html><title>Server lifetime fixture</title>"
    )
    port = unused_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ishiban.cli",
        "serve",
        "--state-directory",
        str(tmp_path),
        "--port",
        str(port),
        cwd=tmp_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await connect_stream(port)
        writer.write(b"GET /api/v1/events?after=0 HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        headers = await reader.readuntil(b"\r\n\r\n")
        assert b"200 OK" in headers, (
            "The test must hold a real active event stream before shutdown."
        )
        process.send_signal(signal.SIGINT)
        async with asyncio.timeout(8):
            await process.wait()
        assert process.returncode == 0, (
            "The API must exit cleanly after cancelling its stream."
        )
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        if process.returncode is None:
            process.kill()
            await process.wait()
