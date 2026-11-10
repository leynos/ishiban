"""Real subprocess boundary tests use a deterministic read-only fake Lody."""

import asyncio
import contextlib as ctx
import sys
import types
import typing as typ

import msgspec
import pytest

from ishiban import lody
from ishiban.lody import read_catalogue

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.protocol import Catalogue


@pytest.mark.asyncio
async def test_catalogue_reader_stops_after_complete_json(
    tmp_path: pathlib.Path,
) -> None:
    """A lingering transport must not hold an already complete snapshot hostage."""
    executable = tmp_path / "fake-lody"
    payload = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [],
    }).decode()
    executable.write_text(
        f"#!{sys.executable}\nimport time\n"
        f"print({payload!r}, flush=True)\ntime.sleep(120)\n"
    )
    executable.chmod(0o700)
    catalogue = await asyncio.wait_for(
        read_catalogue("leynos", str(executable)), timeout=10
    )
    assert catalogue.workspace_id == "workspace", (
        "A complete response must preserve the configured workspace identity."
    )
    assert catalogue.sessions == [], (
        "An explicit empty list must be accepted without waiting for child teardown."
    )


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
