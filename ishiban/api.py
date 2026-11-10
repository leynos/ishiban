"""Falcon read API and bounded replay of committed SQLite projections.

For example, start from ``/api/v1/snapshot`` and open ``/api/v1/events?after=N``
using the returned cursor. Every replay item retains its original projection.
"""

import asyncio
import re
import secrets
import typing as typ

import falcon
import msgspec
from falcon import asgi

from ishiban.activity_api import SessionActivityResource
from ishiban.inspector_api import AgentDetailsResource, PullRequestDetailsResource
from ishiban.interface_state import InterfaceStateCookies, InterfaceStateResource
from ishiban.lazy_activity import LazyActivity
from ishiban.pull_request_details import PullRequestTitles
from ishiban.session_agent import SessionAgentDetails

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.storage import Store

CURSOR_PATTERN = re.compile(r"[0-9]{1,19}\Z")
MAX_CURSOR = 9_223_372_036_854_775_807
HEARTBEAT_POLLS = 60


def parse_cursor(header: str | None, query: str | None) -> int:
    """Parse a safe cursor with Last-Event-ID taking reconnect precedence.

    Returns
    -------
    int
        Validated journal position.

    Raises
    ------
    falcon.HTTPBadRequest
        If the cursor is not a supported nonnegative integer.

    Examples
    --------
    >>> parse_cursor("12", "2")
    12
    """
    value = query if query is not None else "0"
    if header is not None:
        value = header
    if CURSOR_PATTERN.fullmatch(value) is None:
        raise falcon.HTTPBadRequest(description="Cursor must be a nonnegative integer.")
    cursor = int(value)
    if cursor > MAX_CURSOR:
        raise falcon.HTTPBadRequest(description="Cursor exceeds the supported range.")
    return cursor


class Lifecycle:
    """Keep the database connection lifetime inside Falcon's event loop."""

    def __init__(self, store: Store, activity: LazyActivity) -> None:
        """Retain the store; for example, dispose it at ASGI shutdown."""
        self.store = store
        self.activity = activity

    async def process_startup(
        self, scope: cabc.Mapping[str, object], event: cabc.Mapping[str, object]
    ) -> None:
        """Verify the collector-created schema before serving read-only requests."""
        _ = scope, event
        await self.store.initialize(migrate=False)

    async def process_shutdown(
        self, scope: cabc.Mapping[str, object], event: cabc.Mapping[str, object]
    ) -> None:
        """Release SQLAlchemy connections when the server exits."""
        _ = scope, event
        await self.activity.close()
        await self.store.close()

    async def process_response(  # ruff: ignore[no-self-use] - Falcon callback; see developer guide.
        self,
        req: asgi.Request,
        resp: asgi.Response,
        resource: object | None,
        req_succeeded: bool,  # ruff: ignore[boolean-type-hint-positional-argument] - Falcon requires this positional flag.
    ) -> None:
        """Keep local rebuilds and live observations out of heuristic caches.

        For example, reloading after ``bun run build`` fetches the current
        unversioned JavaScript rather than yesterday's interaction handlers.
        """
        _ = req, resource, req_succeeded
        resp.set_header("Cache-Control", "no-store")


class SnapshotResource:
    """Return one transactionally consistent snapshot and its replay cursor."""

    def __init__(
        self, store: Store, workspace_slug: str | None, cookies: InterfaceStateCookies
    ) -> None:
        """Retain the reader; for example, serialize its immutable snapshot."""
        self.store = store
        self.workspace_slug = workspace_slug
        self.cookies = cookies

    async def on_get(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Serve the snapshot; for example, include explicit collector health."""
        snapshot = await self.store.activity_snapshot()
        if self.workspace_slug is not None:
            snapshot["workspaceSlug"] = self.workspace_slug
        snapshot["interfaceState"] = msgspec.to_builtins(self.cookies.read(req))
        resp.media = snapshot


class SessionResource:
    """Expose bounded provenance and latest-known turn records for inspection."""

    def __init__(self, store: Store) -> None:
        """Retain a reader without opening a long-lived transaction."""
        self.store = store

    async def on_get(
        self, _req: asgi.Request, resp: asgi.Response, session_id: str
    ) -> None:
        """Read a session; for example, unknown identities return HTTP 404.

        Raises
        ------
        falcon.HTTPNotFound
            If the requested identity or replay cursor is invalid.
        """
        detail = await self.store.detail(session_id)
        if detail is None:
            raise falcon.HTTPNotFound
        projection = msgspec.convert(detail["session"], type=dict[str, object])
        detail["session"] = (await self.store.restore_activity([projection]))[0]
        resp.media = detail


class EventsResource:
    """Replay bounded committed batches before continuously polling for updates."""

    def __init__(self, store: Store) -> None:
        """Retain the store; for example, query SQLite after every completed batch."""
        self.store = store

    async def on_get(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Resume after the browser's Last-Event-ID when it is present."""
        cursor = parse_cursor(req.get_header("Last-Event-ID"), req.get_param("after"))
        resp.set_header("X-Accel-Buffering", "no")
        resp.sse = self.tail(cursor)

    async def tail(self, cursor: int) -> cabc.AsyncGenerator[asgi.SSEvent]:
        """Yield immutable post-commit events, with periodic comment heartbeats.

        For example, a client pausing between batches uses bounded memory and
        can resume the remaining journal after disconnecting.

        Yields
        ------
        asgi.SSEvent
            Committed replay items or heartbeat comments.
        """
        current_cursor = await self.store.current_cursor()
        if cursor > current_cursor:
            yield asgi.SSEvent(
                event="reset_required",
                json={"reason": "cursor_ahead", "workspaceId": self.store.workspace_id},
            )
            return
        idle = 0
        while True:
            rows = await self.store.events(cursor, limit=100)
            session_rows = [row for row in rows if "sessionId" in row]
            projections = [
                msgspec.convert(row["projection"], type=dict[str, object])
                for row in session_rows
            ]
            views = await self.store.restore_activity(projections)
            for row, view in zip(session_rows, views, strict=True):
                row["projection"] = view
            for row in rows:
                cursor = int(str(row["cursor"]))
                category = "source" if row["source"] == "collector" else "observation"
                yield asgi.SSEvent(json=row, event=category, event_id=str(cursor))
            if rows:
                idle = 0
                continue
            idle += 1
            if idle >= HEARTBEAT_POLLS:
                yield asgi.SSEvent(comment="heartbeat")
                idle = 0
            await asyncio.sleep(0.25)


class HealthResource:
    """Distinguish process liveness from database readiness and source health."""

    def __init__(self, store: Store | None = None) -> None:
        """Select readiness when a store is supplied; otherwise report liveness."""
        self.store = store

    async def on_get(self, _req: asgi.Request, resp: asgi.Response) -> None:
        """Return HTTP 200 only after the requested local health check succeeds."""
        if self.store is not None:
            await self.store.events(0, limit=1)
        resp.media = {"status": "ok"}


def create_app(
    store: Store,
    assets: pathlib.Path | None = None,
    *,
    workspace_slug: str | None = None,
    cookie_secret: bytes | None = None,
) -> asgi.App:
    """Build the read-only ASGI application and optional same-origin static UI.

    For example, ``create_app(store, Path('dist'))`` serves a Bun-built board.

    Returns
    -------
    asgi.App
        Application with read-only API routes and optional static assets.
    """
    activity = LazyActivity(store.workspace_id, workspace_slug or store.workspace_id)
    agent_reader = SessionAgentDetails(
        store.workspace_id, workspace_slug or store.workspace_id
    )
    title_reader = PullRequestTitles()
    cookies = InterfaceStateCookies(cookie_secret or secrets.token_bytes(32))
    app: asgi.App = asgi.App(middleware=[Lifecycle(store, activity)])
    app.add_route("/api/v1/snapshot", SnapshotResource(store, workspace_slug, cookies))
    app.add_route("/api/v1/sessions/{session_id}", SessionResource(store))
    app.add_route(
        "/api/v1/sessions/{session_id}/activity",
        SessionActivityResource(store, activity),
    )
    app.add_route(
        "/api/v1/sessions/{session_id}/agent", AgentDetailsResource(store, agent_reader)
    )
    app.add_route(
        "/api/v1/sessions/{session_id}/pull-requests",
        PullRequestDetailsResource(store, title_reader),
    )
    app.add_route("/api/v1/interface-state", InterfaceStateResource(cookies))
    app.add_route("/api/v1/events", EventsResource(store))
    app.add_route("/health", HealthResource())
    app.add_route("/ready", HealthResource(store))
    if assets is not None and assets.is_dir():
        app.add_static_route("/", assets, fallback_filename="index.html")
    return app
