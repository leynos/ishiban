"""Chunked ASGI requests obey the cumulative activity body limit."""

import asyncio
import typing as typ
from unittest import mock

import pytest
from storage_support import opened_store

from ishiban import bounded_batch
from ishiban.api import create_app
from ishiban.bounded_batch import MAX_BATCH_BODY_BYTES

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


async def _post_chunks(
    app: cabc.Callable[..., cabc.Awaitable[None]], chunks: list[bytes]
) -> tuple[int, bytes]:
    """Post separate ASGI body frames without a Content-Length header.

    For example, two frames of 4,096 bytes exercise cumulative size checks.

    Returns
    -------
    tuple[int, bytes]
        HTTP status and the joined response body from the real Falcon app.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/sessions/activity",
        "raw_path": b"/api/v1/sessions/activity",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 8765),
    }
    frames: list[dict[str, object]] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    requests = iter(frames)
    responses: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        """Yield the next frame after scheduling other ASGI work.

        Returns
        -------
        dict[str, object]
            The next request frame or a transport closure marker.
        """
        await asyncio.sleep(0)
        return next(requests, {"type": "http.disconnect"})

    async def send(message: dict[str, object]) -> None:
        """Capture status and body frames emitted by the mounted route."""
        await asyncio.sleep(0)
        responses.append(message)

    await app(scope, receive, send)
    starts = [part for part in responses if part["type"] == "http.response.start"]
    assert len(starts) == 1, "The ASGI request must produce one HTTP response."
    status = starts[0]["status"]
    assert isinstance(status, int), "The ASGI status must be numeric."
    body = b"".join(
        chunk
        for part in responses
        if part["type"] == "http.response.body"
        for chunk in [part.get("body", b"")]
        if isinstance(chunk, bytes)
    )
    return status, body


@pytest.mark.asyncio
async def test_streamed_activity_body_accepts_exact_limit_and_rejects_next_byte(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 413 precedes decoding when a later frame crosses the byte limit."""
    minimum = b'{"sessionIds":[]}'
    accepted = minimum + b" " * (MAX_BATCH_BODY_BYTES - len(minimum))
    assert len(accepted) == MAX_BATCH_BODY_BYTES, (
        "The accepted request must exercise the exact byte boundary."
    )
    decoder = mock.Mock(wraps=bounded_batch.decode_session_ids)
    monkeypatch.setattr(bounded_batch, "decode_session_ids", decoder)

    async with opened_store(tmp_path) as store:
        app = create_app(store)
        at_limit, response = await _post_chunks(
            app, [accepted[:4_096], accepted[4_096:]]
        )
        assert at_limit == 200, "Exactly 8,192 streamed bytes must be accepted."
        assert response == b"", "An empty member list produces no NDJSON frames."
        decoder.assert_called_once_with(accepted)

        decoder.reset_mock()
        over_limit, _ = await _post_chunks(
            app, [accepted[:4_096], accepted[4_096:] + b" "]
        )
        assert over_limit == 413, (
            "A later frame crossing the cumulative limit must be rejected."
        )
        decoder.assert_not_called()
