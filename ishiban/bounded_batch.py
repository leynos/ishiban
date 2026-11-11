"""Share bounded session-list requests and owned NDJSON response waiters."""

import asyncio
import typing as typ

import falcon
import msgspec
from falcon import asgi

from ishiban.request_body import read_bounded_body
from ishiban.session_identity import is_safe_session_id

if typ.TYPE_CHECKING:
    import collections.abc as cabc

MAX_BATCH_BODY_BYTES = 8_192
MAX_BATCH_SESSIONS = 8
MAX_FRAME_BYTES = 1_048_576
MAX_BATCH_BODY_ERROR = "The activity request body exceeds 8,192 bytes."


class _BatchRequest(msgspec.Struct, rename="camel", forbid_unknown_fields=True):
    """Decode the single public field accepted by both batch endpoints."""

    session_ids: list[str]


def decode_session_ids(body: bytes) -> list[str]:
    """Validate and deduplicate a bounded list in first-seen order.

    For example, ``["s1", "s1", "s2"]`` becomes ``["s1", "s2"]``.

    Returns
    -------
    list[str]
        Unique, safe session identities in request order.

    Raises
    ------
    falcon.HTTPBadRequest
        If the request shape, item count, or identity is invalid.
    """
    try:
        request = msgspec.json.decode(body, type=_BatchRequest)
    except msgspec.DecodeError as error:
        message = 'Body must be an object containing a "sessionIds" string array.'
        raise falcon.HTTPBadRequest(description=message) from error
    if len(request.session_ids) > MAX_BATCH_SESSIONS:
        message = "A batch may contain at most eight session IDs."
        raise falcon.HTTPBadRequest(description=message)
    if any(not is_safe_session_id(session_id) for session_id in request.session_ids):
        message = (
            "Session IDs must be nonempty, at most 256 characters, and contain no NUL."
        )
        raise falcon.HTTPBadRequest(description=message)
    return list(dict.fromkeys(request.session_ids))


async def prepare_batch(
    req: asgi.Request,
    resp: asgi.Response,
    frame_size: cabc.Callable[[str], int],
    *,
    error_message: str,
) -> list[str]:
    """Validate a batch body and frame budget before opening NDJSON.

    For example, recency preflights the longest timestamp and event basis.

    Returns
    -------
    list[str]
        Validated session IDs for the endpoint's own member resolution.

    Raises
    ------
    falcon.HTTPContentTooLarge
        If the body or a preflighted frame exceeds its byte budget.
    """
    body = await read_bounded_body(
        req, max_bytes=MAX_BATCH_BODY_BYTES, error_message=MAX_BATCH_BODY_ERROR
    )
    session_ids = decode_session_ids(body)
    if any(frame_size(session_id) > MAX_FRAME_BYTES for session_id in session_ids):
        raise falcon.HTTPContentTooLarge(description=error_message)
    resp.content_type = "application/x-ndjson"
    resp.set_header("X-Accel-Buffering", "no")
    return session_ids


def start_results[Result](
    candidates: cabc.Iterable[str],
    resolve_one: cabc.Callable[[str], cabc.Coroutine[object, object, Result]],
) -> list[asyncio.Task[Result]]:
    """Start member waiters before emitting immediately available frames.

    For example, a cached activity frame can yield while cold reads start.

    Returns
    -------
    list[asyncio.Task[Result]]
        Tasks owned by this response stream until explicitly reaped.
    """
    return [asyncio.create_task(resolve_one(session_id)) for session_id in candidates]


async def completed_results[Result](
    tasks: list[asyncio.Task[Result]],
) -> cabc.AsyncGenerator[Result]:
    """Yield results as member waiters complete.

    For example, one slow Lody child does not delay a successful sibling.

    Yields
    ------
    Result
        Each independently completed member result.
    """
    for completed in asyncio.as_completed(tasks):
        yield await completed
