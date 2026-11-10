"""Stream bounded, read-only history recency for visible session families."""

import typing as typ

import msgspec
from sqlalchemy.exc import OperationalError

from ishiban.bounded_batch import (
    completed_results,
    prepare_batch,
    start_results,
)
from ishiban.task_ownership import cancel_and_reap

MAX_SQLITE_EVENT_ID = 9_223_372_036_854_775_807

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from falcon import asgi

    from ishiban.session_show import SessionShowReader
    from ishiban.storage import Store


def _frame(
    identity: tuple[str, str],
    basis: int,
    outcome: str,
    latest_history_at: str | None = None,
) -> bytes:
    """Encode one typed member with its execution basis and newline.

    Returns
    -------
    bytes
        One scoped NDJSON frame within the preflighted identity bound.
    """
    frame: dict[str, object] = {
        "workspaceId": identity[0],
        "sessionId": identity[1],
        "lastActivityEventId": basis,
        "outcome": outcome,
    }
    if outcome == "available":
        frame["latestHistoryAt"] = latest_history_at
    return msgspec.json.encode(frame) + b"\n"


class SessionRecencyResource:
    """Read at most eight raw session identities with shared show ownership."""

    def __init__(self, store: Store, reader: SessionShowReader) -> None:
        """Retain the raw journal reader and one shared Lody show service."""
        self.store = store
        self.reader = reader

    async def on_post(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Preflight scope size before opening a streaming metadata response.

        For example, a visible family submits ``{"sessionIds":["root","child"]}``.

        """
        session_ids = await prepare_batch(
            req,
            resp,
            lambda session_id: len(
                _frame(
                    (self.store.workspace_id, session_id),
                    MAX_SQLITE_EVENT_ID,
                    "available",
                    "x" * 64,
                )
            ),
            error_message="A session recency identity exceeds the frame limit.",
        )
        resp.stream = self._stream_results(session_ids)

    async def _stream_results(
        self, session_ids: list[str]
    ) -> cabc.AsyncGenerator[bytes]:
        """Yield independently completed results and reap request waiters.

        Yields
        ------
        bytes
            One available or unavailable outcome per unique raw session.
        """
        tasks = start_results(session_ids, self._resolve_one)
        try:
            async for frame in completed_results(tasks):
                yield frame
        finally:
            await cancel_and_reap(tasks)

    async def _resolve_one(self, session_id: str) -> bytes:
        """Contain missing identities and expected storage failures per member.

        Returns
        -------
        bytes
            A scoped outcome that echoes the read execution watermark.
        """
        basis = 0
        identity = (self.store.workspace_id, session_id)
        try:
            projection = await self.store.session_projection(session_id)
            if projection is None:
                return _frame(identity, basis, "unavailable")
            basis = int(str(projection.get("lastActivityEventId") or 0))
            metadata = await self.reader.read(session_id, basis)
        except OperationalError:
            metadata = None
        if metadata is None:
            return _frame(identity, basis, "unavailable")
        return _frame(
            identity,
            basis,
            "available",
            metadata.latest_history_at,
        )
