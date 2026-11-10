"""Cache on-demand runtime evidence while leaving the durable journal untouched.

For example, a visible metadata-only mark may resolve to idle without appending
an observation event or changing the snapshot's replay cursor.
"""

import time
import typing as typ

import falcon

from ishiban.storage.projections import apply_observation

if typ.TYPE_CHECKING:
    from falcon import asgi

    from ishiban.lazy_activity import LazyActivity
    from ishiban.storage import Store


class SessionActivityResource:
    """Read one current projection and optionally enrich unknown activity."""

    def __init__(self, store: Store, activity: LazyActivity) -> None:
        """Retain the two readers; for example, neither owns journal writes."""
        self.store = store
        self.activity = activity

    async def on_get(
        self, _req: asgi.Request, resp: asgi.Response, session_id: str
    ) -> None:
        """Resolve a known session without fabricating durable evidence.

        For example, a metadata-only CLI result leaves the session unresolved.

        Raises
        ------
        falcon.HTTPNotFound
            If the session does not exist in the bound workspace.
        """
        previous = await self.store.session_projection(session_id)
        if previous is None:
            raise falcon.HTTPNotFound
        projection: dict[str, object] | None = None
        if previous.get("state") == "unknown":
            cached = (await self.store.restore_activity([previous]))[0]
            if cached.get("activitySource") == "lazy":
                resp.media = {"workspaceId": self.store.workspace_id, "session": cached}
                return
            revision = int(str(previous["lastEventId"]))
            observed = await self.activity.read(session_id, revision)
            if observed is not None:
                projection = apply_observation(
                    previous, observed, 0, time.time_ns() // 1_000_000
                )
                for key in (
                    "machineId",
                    "title",
                    "archived",
                    "removed",
                    "lastEvidenceGeneration",
                ):
                    projection[key] = previous.get(key)
                projection["activitySource"] = "lazy"
                projection = await self.store.remember_activity(projection)
        resp.media = {"workspaceId": self.store.workspace_id, "session": projection}
