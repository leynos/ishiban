"""Stream bounded session activity lookups as newline-delimited JSON."""

import asyncio
import typing as typ

import falcon
import msgspec
from falcon import asgi
from sqlalchemy.exc import OperationalError

from ishiban.activity_api import resolve_activity, restore_cached_activities
from ishiban.request_body import read_bounded_body

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from ishiban.lazy_activity import LazyActivity
    from ishiban.storage import Store

MAX_BATCH_BODY_BYTES = 8_192
MAX_BATCH_SESSIONS = 8
MAX_SESSION_ID_CHARS = 256
MAX_BATCH_BODY_ERROR = "The activity request body exceeds 8,192 bytes."


class _ActivityBatchRequest(msgspec.Struct, rename="camel", forbid_unknown_fields=True):
    """Decode the single public field accepted by the batch endpoint."""

    session_ids: list[str]


class BatchSessionActivityResource:
    """Resolve a small session set and stream each completed result promptly."""

    def __init__(self, store: Store, activity: LazyActivity) -> None:
        """Retain the shared journal reader and observer service."""
        self.store = store
        self.activity = activity

    async def on_post(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Validate a bounded JSON list and open its NDJSON response stream.

        For example, ``{"sessionIds": ["s1", "s2"]}`` produces two frames.
        """
        body = await read_bounded_body(
            req, max_bytes=MAX_BATCH_BODY_BYTES, error_message=MAX_BATCH_BODY_ERROR
        )
        session_ids = _decode_session_ids(body)
        resp.content_type = "application/x-ndjson"
        resp.set_header("X-Accel-Buffering", "no")
        resp.stream = self._stream_results(session_ids)

    async def _stream_results(
        self, session_ids: list[str]
    ) -> cabc.AsyncGenerator[bytes]:
        """Yield cache hits before starting or awaiting fresh activity reads.

        For example, a cached result is emitted before any slower Lody lookup.

        Yields
        ------
        bytes
            One compact JSON object and newline for each unique session ID.
        """
        cached, immediate_ids, pending_ids = await self._prepare_batch(session_ids)
        tasks = [
            asyncio.create_task(self._resolve_one(session_id))
            for session_id in pending_ids
        ]

        try:
            for session_id, projection in cached:
                yield _encode_frame(self.store.workspace_id, session_id, projection)
            for session_id in immediate_ids:
                yield _encode_frame(self.store.workspace_id, session_id, None)
            for completed in asyncio.as_completed(tasks):
                session_id, projection = await completed
                yield _encode_frame(self.store.workspace_id, session_id, projection)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                # LazyActivity owns the shared subprocess tasks; this reaps only
                # the request waiters created for this response stream.
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _prepare_batch(
        self, session_ids: list[str]
    ) -> tuple[list[tuple[str, dict[str, object]]], list[str], list[str]]:
        """Separate cached hits, known/missing rows, and fresh lookup candidates.

        Returns
        -------
        tuple[list[tuple[str, dict[str, object]]], list[str], list[str]]
            Cached frames, immediate null frames, and pending observer identities.
        """
        previous = [
            await self.store.session_projection(session_id)
            for session_id in session_ids
        ]
        cache_indexes: list[int] = []
        cache_candidates: list[dict[str, object]] = []
        for index, projection in enumerate(previous):
            if projection is not None and projection.get("state") == "unknown":
                cache_indexes.append(index)
                cache_candidates.append(projection)
        cached_values = await restore_cached_activities(self.store, cache_candidates)

        cached: list[tuple[str, dict[str, object]]] = []
        cached_ids: set[str] = set()
        for index, projection in zip(cache_indexes, cached_values, strict=True):
            if projection is not None:
                session_id = session_ids[index]
                cached.append((session_id, projection))
                cached_ids.add(session_id)

        immediate_ids: list[str] = []
        pending_ids: list[str] = []
        for session_id, projection in zip(session_ids, previous, strict=True):
            if projection is None or projection.get("state") != "unknown":
                immediate_ids.append(session_id)
            elif session_id not in cached_ids:
                pending_ids.append(session_id)
        return cached, immediate_ids, pending_ids

    async def _resolve_one(
        self, session_id: str
    ) -> tuple[str, dict[str, object] | None]:
        """Contain missing identities and operational storage failures per member.

        Returns
        -------
        tuple[str, dict[str, object] or None]
            The input identity and its optional lazy projection.
        """
        try:
            return session_id, await resolve_activity(
                self.store, self.activity, session_id
            )
        except falcon.HTTPNotFound, OperationalError:
            return session_id, None


def _decode_session_ids(body: bytes) -> list[str]:
    """Validate identifiers and deduplicate them in first-seen order.

    For example, ``["s1", "s1", "s2"]`` becomes ``["s1", "s2"]``.

    Returns
    -------
    list[str]
        Unique validated session identities in request order.

    Raises
    ------
    falcon.HTTPBadRequest
        If the body shape, item count, or any identifier is invalid.
    """
    try:
        request = msgspec.json.decode(body, type=_ActivityBatchRequest)
    except msgspec.DecodeError as error:
        message = 'Body must be an object containing a "sessionIds" string array.'
        raise falcon.HTTPBadRequest(description=message) from error

    if len(request.session_ids) > MAX_BATCH_SESSIONS:
        message = "A batch may contain at most eight session IDs."
        raise falcon.HTTPBadRequest(description=message)
    if any(
        not session_id or len(session_id) > MAX_SESSION_ID_CHARS or "\0" in session_id
        for session_id in request.session_ids
    ):
        message = (
            "Session IDs must be nonempty, at most 256 characters, and contain no NUL."
        )
        raise falcon.HTTPBadRequest(description=message)
    return list(dict.fromkeys(request.session_ids))


def _encode_frame(
    workspace_id: str, session_id: str, projection: dict[str, object] | None
) -> bytes:
    """Encode one stable event-loop result as a newline-delimited frame.

    Returns
    -------
    bytes
        The compact JSON object followed by exactly one newline.
    """
    return (
        msgspec.json.encode({
            "workspaceId": workspace_id,
            "sessionId": session_id,
            "session": projection,
        })
        + b"\n"
    )
