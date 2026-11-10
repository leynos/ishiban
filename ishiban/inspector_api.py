"""Read inspector metadata lazily without exposing configuration secrets.

For example, the inspector may resolve a configuration display name while the
Lody CLI session identity remains available immediately from its projection.
"""

import typing as typ

import falcon
import msgspec

from ishiban.domain import PullRequest

if typ.TYPE_CHECKING:
    from falcon import asgi

    from ishiban.pull_request_details import PullRequestTitles
    from ishiban.session_agent import SessionAgentDetails
    from ishiban.storage import Store


class AgentDetailsResource:
    """Expose only cached agent type and configuration identity/name."""

    def __init__(self, store: Store, reader: SessionAgentDetails) -> None:
        """Retain readers only; for example, never update session metadata."""
        self.store = store
        self.reader = reader

    async def on_get(
        self, _req: asgi.Request, resp: asgi.Response, session_id: str
    ) -> None:
        """Return inspector metadata for an existing workspace session.

        For example, an unreadable configuration leaves its name unavailable.

        Raises
        ------
        falcon.HTTPNotFound
            If the Lody session is absent from this workspace's journal.
        """
        if await self.store.session_projection(session_id) is None:
            raise falcon.HTTPNotFound
        agent = await self.reader.read(session_id)
        resp.media = {
            "workspaceId": self.store.workspace_id,
            "sessionId": session_id,
            "agent": msgspec.to_builtins(agent),
        }


class PullRequestDetailsResource:
    """Fill missing PR titles for the selected existing session only."""

    def __init__(self, store: Store, reader: PullRequestTitles) -> None:
        """Retain readers; for example, merged PRs can resolve a missing name."""
        self.store = store
        self.reader = reader

    async def on_get(
        self, _req: asgi.Request, resp: asgi.Response, session_id: str
    ) -> None:
        """Read missing titles without changing stored workflow classification.

        For example, a merged PR keeps its stage while gaining a display name.

        Raises
        ------
        falcon.HTTPNotFound
            If the session is not known in this workspace.
        """
        projection = await self.store.session_projection(session_id)
        if projection is None:
            raise falcon.HTTPNotFound
        prs = msgspec.convert(
            projection.get("pullRequests", []), type=list[PullRequest]
        )
        urls = [pr.url for pr in prs if not (pr.title or "").strip()]
        titles = await self.reader.read(urls)
        resp.media = {
            "workspaceId": self.store.workspace_id,
            "sessionId": session_id,
            "titles": titles,
        }
