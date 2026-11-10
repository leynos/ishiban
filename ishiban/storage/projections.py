"""Pure session projection updates applied inside journal transactions."""

import typing as typ

from ishiban.domain import Turn

if typ.TYPE_CHECKING:
    from ishiban.domain import CatalogueEntry, Envelope, ObservedSession

type SessionProjection = dict[str, object]


def empty_session(session_id: str, machine_id: str = "") -> SessionProjection:
    """Return an unclassified session with no persisted evidence.

    Returns
    -------
    SessionProjection
        The complete public session shape with unknown activity and stage.
    """
    return {
        "sessionId": session_id,
        "machineId": machine_id,
        "title": "",
        "archived": False,
        "removed": False,
        "state": "unknown",
        "source": "metadata",
        "freshness": "unavailable",
        "repoFullName": None,
        "branchName": None,
        "stage": "unclassified",
        "stageReason": "No catalogue entry is available.",
        "pullRequests": [],
        "latestTurn": None,
        "activeTurns": [],
        "lastEvidenceGeneration": None,
        "lastMetadataGeneration": None,
        "lastObservedAt": None,
        "lastEventId": 0,
    }


def apply_observation(
    existing: SessionProjection | None,
    observed: ObservedSession,
    generation: int,
    observed_at: int,
) -> SessionProjection:
    """Merge persisted evidence or metadata without erasing known outcomes.

    Returns
    -------
    SessionProjection
        The updated session while preserving durable state on metadata input.
    """
    projection = (
        empty_session(observed.session_id, observed.machine_id)
        if existing is None
        else dict(existing)
    )
    projection.update({
        "sessionId": observed.session_id,
        "machineId": observed.machine_id,
        "title": observed.title,
        "archived": observed.archived,
        "removed": False,
        "source": observed.source,
        "freshness": observed.freshness,
    })

    if observed.source == "persisted":
        projection.update({
            "state": observed.state,
            "latestTurn": _turn_projection(observed.latest_turn),
            "activeTurns": [_turn_projection(turn) for turn in observed.active_turns],
            "lastEvidenceGeneration": generation,
            "lastObservedAt": observed_at,
        })
    else:
        projection["lastMetadataGeneration"] = generation
        if existing is None:
            projection["state"] = "unknown"
    return projection


def apply_turn_event(
    existing: SessionProjection | None,
    envelope: Envelope,
    generation: int,
) -> SessionProjection:
    """Apply one named turn transition, including unmatched finishes.

    Returns
    -------
    SessionProjection
        The session with the named turn's latest transition applied.
    """
    session_id = envelope.session_id or ""
    projection = empty_session(session_id) if existing is None else dict(existing)
    turn = _event_turn(envelope)
    user_turn_id = envelope.user_turn_id or ""
    active_turns = [
        item
        for item in _projection_list(projection, "activeTurns")
        if _projection_string(item, "userTurnId") != user_turn_id
    ]
    if envelope.type == "turn.started":
        active_turns.append(turn)

    projection.update({
        "removed": False,
        "source": "persisted",
        "freshness": "synced",
        "latestTurn": turn,
        "activeTurns": active_turns,
        "lastEvidenceGeneration": generation,
        "lastObservedAt": envelope.observed_at,
    })
    return projection


def apply_removal(
    existing: SessionProjection | None, session_id: str
) -> SessionProjection:
    """Tombstone a session while retaining its current evidence and turns.

    Returns
    -------
    SessionProjection
        The retained session with ``removed`` set to true.
    """
    projection = empty_session(session_id) if existing is None else dict(existing)
    projection["removed"] = True
    return projection


def apply_catalogue(
    existing: SessionProjection | None,
    entry: CatalogueEntry,
    generation: int,
) -> SessionProjection:
    """Merge read-only repository and pull-request metadata.

    Returns
    -------
    SessionProjection
        The session with catalogue fields and metadata generation updated.
    """
    projection = (
        empty_session(entry.session_id, entry.machine_id)
        if existing is None
        else dict(existing)
    )
    projection.update({
        "machineId": entry.machine_id,
        "title": entry.title,
        "archived": entry.archived,
        "repoFullName": entry.repo_full_name,
        "branchName": entry.branch_name,
        "pullRequests": [
            {
                "url": request.url,
                "title": request.title,
                "status": request.status,
            }
            for request in entry.pull_requests
        ],
        "stage": entry.stage,
        "stageReason": entry.stage_reason,
        "lastMetadataGeneration": generation,
    })
    return projection


def _turn_projection(turn: Turn | None) -> dict[str, object] | None:
    """Convert a typed turn to its bounded camel-case public shape.

    Returns
    -------
    dict[str, object] or None
        A JSON-ready turn projection, or ``None`` when no turn is known.
    """
    if turn is None:
        return None
    return _turn_fields(turn)


def _event_turn(envelope: Envelope) -> dict[str, object]:
    """Build the same public turn shape for a start or finish event.

    Returns
    -------
    dict[str, object]
        The latest known public fields for the event's turn.
    """
    state = (
        "running" if envelope.type == "turn.started" else envelope.outcome or "unknown"
    )
    return _turn_fields(
        Turn(
            user_turn_id=envelope.user_turn_id or "",
            state=state,
            assistant_turn_id=envelope.assistant_turn_id,
            duration_ms=envelope.duration_ms,
            error=envelope.error,
        )
    )


def _turn_fields(turn: Turn) -> dict[str, object]:
    """Encode the shared turn shape for snapshots and incremental events.

    For example, absent duration and assistant identity omit those JSON keys.

    Returns
    -------
    dict[str, object]
        Required identity and state with only available optional fields.
    """
    projection: dict[str, object] = {
        "userTurnId": turn.user_turn_id,
        "state": turn.state,
    }
    if turn.assistant_turn_id is not None:
        projection["assistantTurnId"] = turn.assistant_turn_id
    if turn.duration_ms is not None:
        projection["durationMs"] = turn.duration_ms
    if turn.state == "failed" and turn.error:
        projection["error"] = turn.error[:4096]
    return projection


def _projection_list(projection: SessionProjection, key: str) -> list[object]:
    """Return a projection list while keeping JSON input narrowly typed.

    Returns
    -------
    list[object]
        The list value, or an empty list for a missing or invalid field.
    """
    value = projection.get(key)
    return typ.cast("list[object]", value) if isinstance(value, list) else []


def _projection_string(projection: object, key: str) -> str:
    """Read a string field from a decoded projection object.

    Returns
    -------
    str
        The field value, or an empty string when it is missing or non-string.
    """
    if not isinstance(projection, dict):
        return ""
    value = typ.cast("dict[str, object]", projection).get(key)
    return value if isinstance(value, str) else ""
