"""Decode bounded Lody catalogue and observer messages at the trust boundary.

For example, ``decode_event(line, workspace, position)`` rejects a foreign
workspace or a gap before any database mutation occurs.
"""

import dataclasses as dc

import msgspec

from ishiban.domain import Envelope

SESSION_STATES = frozenset({"idle", "pending", "running", "waiting", "unknown"})
EVENT_TYPES = frozenset({
    "snapshot",
    "ready",
    "session.changed",
    "turn.started",
    "turn.finished",
    "session.removed",
})
TURN_STATES = frozenset({
    "pending",
    "running",
    "unknown",
    "completed",
    "failed",
    "canceled",
})
MAX_LINE_BYTES = 1_048_576


class ProtocolError(ValueError):
    """The observer contract cannot be interpreted without losing evidence."""


@dc.dataclass(slots=True)
class StreamPosition:
    """Sequence state scoped to exactly one child process."""

    stream_id: str | None = None
    sequence: int = 0


class RawPR(msgspec.Struct, rename="camel", kw_only=True):
    """Read-only PR summary; for example, status is draft or open."""

    url: str
    status: str = "unknown"


class RawSession(msgspec.Struct, rename="camel", kw_only=True):
    """Catalogue identity and explicitly supplied associations."""

    id: str
    machine_id: str = ""
    title: str = "Untitled session"
    is_archived: bool = False
    repo_full_name: str | None = None
    branch_name: str | None = None
    pull_requests: list[RawPR] = msgspec.field(default_factory=list)


class Catalogue(msgspec.Struct, rename="camel", kw_only=True):
    """A complete catalogue response; for example, ``ok`` must be true."""

    ok: bool
    workspace_id: str
    sessions: list[RawSession]


def decode_catalogue(data: bytes) -> Catalogue:
    """Decode a successful catalogue without treating omissions as deletion.

    For example, an ``ok: false`` response is rejected even with an empty list.

    Returns
    -------
    Catalogue
        The typed successful response.

    Raises
    ------
    ProtocolError
        If the response does not confirm a workspace snapshot.
    """
    catalogue = msgspec.json.decode(data, type=Catalogue)
    if not catalogue.ok or not catalogue.workspace_id:
        message = "Catalogue response is not a successful workspace snapshot."
        raise ProtocolError(message)
    identities = [session.id for session in catalogue.sessions]
    if any(not identity for identity in identities) or len(set(identities)) != len(
        identities
    ):
        message = "Catalogue has missing or duplicate session identities."
        raise ProtocolError(message)
    return catalogue


def decode_event(data: bytes, workspace_id: str, position: StreamPosition) -> Envelope:
    """Validate one v1 observer record before advancing its process position.

    For example, a sequence jump from one to three raises ``ProtocolError``.

    Returns
    -------
    Envelope
        The validated event with the position advanced.

    Raises
    ------
    ProtocolError
        If identity, sequence, schema, or payload is invalid.
    """
    if len(data) > MAX_LINE_BYTES:
        message = "Observer record exceeds the one-megabyte limit."
        raise ProtocolError(message)
    try:
        event = msgspec.json.decode(data, type=Envelope)
    except msgspec.DecodeError as error:
        message = "Observer record is not a valid v1 envelope."
        raise ProtocolError(message) from error
    _validate_identity(event, workspace_id, position)
    _validate_payload(event)
    position.stream_id = event.stream_id
    position.sequence = event.sequence
    return event


def _validate_identity(
    event: Envelope, workspace: str, position: StreamPosition
) -> None:
    """Reject identity changes; for example, a child cannot change workspace.

    Raises
    ------
    ProtocolError
        If version, workspace, stream identity, or sequence is invalid.
    """
    if event.version != 1 or event.workspace_id != workspace:
        message = "Unknown version or foreign workspace in observer stream."
        raise ProtocolError(message)
    if not event.stream_id or event.sequence != position.sequence + 1:
        message = "Observer sequence is missing, duplicated, or out of order."
        raise ProtocolError(message)
    if position.stream_id is not None and event.stream_id != position.stream_id:
        message = "Observer stream identity changed within one child process."
        raise ProtocolError(message)
    if event.observed_at < 0:
        message = "Observer timestamp must be nonnegative."
        raise ProtocolError(message)


def _validate_payload(event: Envelope) -> None:
    """Check event-specific fields; for example, turn completion needs an outcome.

    Raises
    ------
    ProtocolError
        If the event type or its required fields are invalid.
    """
    if event.type not in EVENT_TYPES:
        message = "Unknown observer event type."
        raise ProtocolError(message)
    if event.type == "ready":
        return
    if not event.session_id:
        message = "Session event is missing its stable identity."
        raise ProtocolError(message)
    if event.type in {"snapshot", "session.changed"}:
        _validate_session(event)
    if event.type in {"turn.started", "turn.finished"} and not event.user_turn_id:
        message = "Turn event is missing the user turn identity."
        raise ProtocolError(message)
    if event.type == "turn.finished" and event.outcome not in {
        "completed",
        "failed",
        "canceled",
    }:
        message = "Turn completion has an unknown outcome."
        raise ProtocolError(message)


def _validate_session(event: Envelope) -> None:
    """Validate projection identity and enums before accepting a snapshot.

    Raises
    ------
    ProtocolError
        If projection identity, state, or evidence fields are invalid.
    """
    session = event.session
    if session is None or session.session_id != event.session_id:
        message = "Session projection identity does not match the event."
        raise ProtocolError(message)
    if session.state not in SESSION_STATES or session.source not in {
        "metadata",
        "persisted",
    }:
        message = "Session state or evidence source is unknown."
        raise ProtocolError(message)
    if session.freshness not in {"synced", "unavailable"}:
        message = "Session evidence freshness is unknown."
        raise ProtocolError(message)
    turns = [*session.active_turns]
    if session.latest_turn is not None:
        turns.append(session.latest_turn)
    if any(turn.state not in TURN_STATES or not turn.user_turn_id for turn in turns):
        message = "Turn projection has an invalid state or identity."
        raise ProtocolError(message)
