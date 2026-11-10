"""Pure runtime-field selection and revision-safe sidecar overlays."""

import msgspec

RUNTIME_FIELDS = (
    "state",
    "latestTurn",
    "activeTurns",
    "lastObservedAt",
    "source",
    "freshness",
)


def _activity_revision(projection: dict[str, object]) -> int | None:
    """Parse the optional activity-event revision, defaulting a missing value to zero.

    Returns
    -------
    int or None
        Parsed event revision, or ``None`` if the supplied value is invalid.
    """
    value = projection.get("lastActivityEventId", 0)
    match value:
        case None:
            return 0
        case bool():
            return None
        case int() if value >= 0:
            return value
        case str() if value.isdecimal():
            return int(value)
        case _:
            return None


def _runtime_json(projection: dict[str, object]) -> str:
    """Serialize only runtime fields, excluding durable metadata and identifiers.

    Returns
    -------
    str
        Compact JSON containing only known runtime projection fields.
    """
    runtime = {
        field: projection[field] for field in RUNTIME_FIELDS if field in projection
    }
    return msgspec.json.encode(runtime).decode("utf-8")


def _cache_candidate_session_id(projection: dict[str, object]) -> str | None:
    """Return an unknown projection's identity when its overlay guard is valid.

    Returns
    -------
    str or None
        Eligible session ID, or ``None`` when the projection must stay unchanged.
    """
    if projection.get("state") != "unknown":
        return None
    if projection.get("removed", False) is not False:
        return None
    session_id = projection.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None
    if _activity_revision(projection) is None:
        return None
    return session_id


def _merge_projection(
    projection: dict[str, object],
    cache_record: tuple[int, str] | None,
) -> dict[str, object]:
    """Overlay cached runtime only when no newer activity event supersedes it.

    Returns
    -------
    dict of str to object
        A copy of the incoming projection with eligible cached runtime restored.
    """
    if projection.get("state") != "unknown":
        return dict(projection)
    if projection.get("removed", False) is not False:
        return dict(projection)
    if cache_record is None:
        return dict(projection)
    activity_revision = _activity_revision(projection)
    if activity_revision is None or activity_revision > cache_record[0]:
        return dict(projection)
    try:
        runtime = msgspec.json.decode(cache_record[1], type=dict[str, object])
    except msgspec.DecodeError:
        return dict(projection)
    restored = dict(projection)
    restored.update({
        field: runtime[field] for field in RUNTIME_FIELDS if field in runtime
    })
    restored["activitySource"] = "lazy"
    return restored
