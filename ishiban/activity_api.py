"""Cache on-demand runtime evidence while leaving the durable journal untouched.

For example, a visible metadata-only mark may resolve to idle without appending
an observation event or changing the snapshot's replay cursor.
"""

import time
import typing as typ

import falcon

from ishiban.public_projection import public_session
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
        self, req: asgi.Request, resp: asgi.Response, session_id: str
    ) -> None:
        """Resolve a known session without fabricating durable evidence.

        For example, a metadata-only CLI result leaves the session unresolved.

        """
        projection = await resolve_activity(
            self.store,
            self.activity,
            session_id,
            include_known=req.get_param_as_bool("includeKnown") is True,
        )
        resp.media = {
            "workspaceId": self.store.workspace_id,
            "session": public_session(projection) if projection is not None else None,
        }


async def resolve_activity(
    store: Store,
    activity: LazyActivity,
    session_id: str,
    *,
    include_known: bool = False,
) -> dict[str, object] | None:
    """Resolve one unknown session using cache and revision-safe observation.

    For example, a cached lazy result is returned without starting another Lody
    request, while a missing session raises ``HTTPNotFound``.

    Returns
    -------
    dict[str, object] or None
        The lazy projection, or ``None`` for known or unavailable activity.

    Raises
    ------
    falcon.HTTPNotFound
        If the identity is absent from the configured workspace.
    """
    previous = await store.session_projection(session_id)
    if previous is None:
        raise falcon.HTTPNotFound
    if previous.get("state") != "unknown":
        if include_known:
            return (await store.restore_activity([previous]))[0]
        return None

    cached = await restore_cached_activities(store, [previous])
    if cached[0] is not None:
        return cached[0]

    revision = int(str(previous.get("lastActivityEventId", 0)))
    observed = await activity.read(session_id, revision)
    if observed is None:
        return None

    projection = apply_observation(previous, observed, 0, time.time_ns() // 1_000_000)
    for key in (
        "machineId",
        "title",
        "archived",
        "removed",
        "lastEvidenceGeneration",
    ):
        projection[key] = previous.get(key)
    projection["activitySource"] = "lazy"
    return await store.remember_activity(projection)


async def restore_cached_activities(
    store: Store, projections: list[dict[str, object]]
) -> list[dict[str, object] | None]:
    """Restore only cache hits while preserving input order for a request batch.

    For example, an unknown session without a retained cache entry maps to
    ``None`` and remains eligible for a fresh observer read.

    Returns
    -------
    list[dict[str, object] or None]
        Lazy projections aligned with the supplied session projections.
    """
    if not projections:
        return []
    restored = await store.restore_activity(projections)
    return [
        projection if projection.get("activitySource") == "lazy" else None
        for projection in restored
    ]
