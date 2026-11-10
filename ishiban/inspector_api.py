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


async def _existing_session(store: Store, session_id: str) -> dict[str, object]:
    """Load one current inspector session or reject an absent identity.

    For example, a missing child tab never triggers a Lody or GitHub read.

    Returns
    -------
    dict[str, object]
        The current session projection from this workspace.

    Raises
    ------
    falcon.HTTPNotFound
        If no projection exists for the requested session.
    """
    projection = await store.session_projection(session_id)
    if projection is None:
        raise falcon.HTTPNotFound
    return projection


def _set_scoped_detail(
    resp: asgi.Response,
    identity: tuple[str, str],
    field: str,
    value: object,
) -> None:
    """Scope one inspector-only value to its current workspace and session.

    For example, agent labels and PR titles use the same identity envelope,
    while their resolution and public payloads remain endpoint-specific.
    """
    resp.media = {
        "workspaceId": identity[0],
        "sessionId": identity[1],
        field: value,
    }


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

        """
        projection = await _existing_session(self.store, session_id)
        basis = int(str(projection.get("lastActivityEventId") or 0))
        agent = await self.reader.read(session_id, basis)
        _set_scoped_detail(
            resp,
            (self.store.workspace_id, session_id),
            "agent",
            msgspec.to_builtins(agent),
        )


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

        """
        projection = await _existing_session(self.store, session_id)
        prs = msgspec.convert(
            projection.get("pullRequests", []), type=list[PullRequest]
        )
        urls = [pr.url for pr in prs if not (pr.title or "").strip()]
        titles = await self.reader.read(urls)
        _set_scoped_detail(
            resp, (self.store.workspace_id, session_id), "titles", titles
        )
