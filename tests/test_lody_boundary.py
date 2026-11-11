"""Real subprocess boundary tests use a deterministic read-only fake Lody."""

import asyncio
import contextlib as ctx
import signal
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
