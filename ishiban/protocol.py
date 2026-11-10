"""Decode bounded Lody catalogue and observer messages at the trust boundary.

For example, ``decode_event(line, workspace, position)`` rejects a foreign
workspace or a gap before any database mutation occurs.
"""

import dataclasses as dc
import typing as typ

import msgspec

from ishiban.domain import Envelope, Turn

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from ishiban.domain import ObservedSession

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
    parent_session_id: str | None = None
    created_at: str | None = None


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
    _validate_catalogue_identities(catalogue)
    return catalogue


def _validate_catalogue_identities(catalogue: Catalogue) -> None:
    """Reject missing or repeated identities in one complete catalogue.

    For example, duplicate rows cannot be mistaken for independent sessions.

    Raises
    ------
    ProtocolError
        If any catalogue identity is empty or repeated.
    """
    identities = {session.id for session in catalogue.sessions}
    if "" in identities or len(identities) != len(catalogue.sessions):
        message = "Catalogue has missing or duplicate session identities."
        raise ProtocolError(message)


def decode_event(data: bytes, workspace_id: str, position: StreamPosition) -> Envelope:
    """Validate one v1 observer record before advancing its process position.

    For example, a sequence jump from one to three raises ``ProtocolError``.

    Returns
    -------
    Envelope
        The validated event with the position advanced.

    """
    event = _decode_envelope(data)
    _validate_identity(event, workspace_id, position)
    _validate_payload(event)
    position.stream_id = event.stream_id
    position.sequence = event.sequence
    return event


def _decode_envelope(data: bytes) -> Envelope:
    """Bound and decode one observer transport record before semantic checks.

    For example, oversized or malformed lines never advance stream position.

    Returns
    -------
    Envelope
        Decoded observer record ready for semantic validation.

    Raises
    ------
    ProtocolError
        If the record exceeds its size bound or is not valid JSON.
    """
    if len(data) > MAX_LINE_BYTES:
        message = "Observer record exceeds the one-megabyte limit."
        raise ProtocolError(message)
    try:
        return msgspec.json.decode(data, type=Envelope)
    except msgspec.DecodeError as error:
        message = "Observer record is not a valid v1 envelope."
        raise ProtocolError(message) from error


def _validate_identity(
    event: Envelope, workspace: str, position: StreamPosition
) -> None:
    """Reject identity changes; for example, a child cannot change workspace.

    Raises
    ------
    ProtocolError
        If version, workspace or timestamp is invalid.
    """
    if (event.version, event.workspace_id) != (1, workspace):
        message = "Unknown version or foreign workspace in observer stream."
        raise ProtocolError(message)
    _validate_stream_position(event, position)
    if event.observed_at < 0:
        message = "Observer timestamp must be nonnegative."
        raise ProtocolError(message)


def _validate_stream_position(event: Envelope, position: StreamPosition) -> None:
    """Check process-local stream identity and contiguous sequence order.

    For example, reconnecting starts a new position rather than reusing one.

    Invalid stream or sequence facts raise ``ProtocolError``.
    """
    sequence_error = "Observer sequence is missing, duplicated, or out of order."
    _require_rules((
        (bool(event.stream_id), sequence_error),
        (event.sequence == position.sequence + 1, sequence_error),
        (
            position.stream_id is None or event.stream_id == position.stream_id,
            "Observer stream identity changed within one child process.",
        ),
    ))


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
    validator = _EVENT_VALIDATORS.get(event.type)
    if validator is not None:
        validator(event)


def _validate_turn_event(event: Envelope) -> None:
    """Require a turn identity and a known terminal outcome when finishing.

    For example, a started turn requires identity but has no terminal outcome.

    Invalid turn identity or outcome raises ``ProtocolError``.
    """
    _require_rules((
        (bool(event.user_turn_id), "Turn event is missing the user turn identity."),
        (
            event.type != "turn.finished"
            or event.outcome in {"completed", "failed", "canceled"},
            "Turn completion has an unknown outcome.",
        ),
    ))


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
    _validate_session_evidence(session)
    _validate_session_turns(session)


def _validate_session_evidence(session: ObservedSession) -> None:
    """Admit only observed activity, provenance, and freshness vocabulary.

    For example, an arbitrary source label cannot become durable evidence.

    Unknown state, source or freshness raises ``ProtocolError``.
    """
    rules = (
        (session.state, SESSION_STATES, "Session state or evidence source is unknown."),
        (
            session.source,
            {"metadata", "persisted"},
            "Session state or evidence source is unknown.",
        ),
        (
            session.freshness,
            {"synced", "unavailable"},
            "Session evidence freshness is unknown.",
        ),
    )
    _require_rules((value in allowed, message) for value, allowed, message in rules)


def _require_rules(rules: cabc.Iterable[tuple[bool, str]]) -> None:
    """Apply ordered protocol checks without obscuring their error provenance.

    For example, the first invalid field stops validation with its own message.

    Raises
    ------
    ProtocolError
        If any rule fails in the supplied order.
    """
    for is_valid, message in rules:
        if not is_valid:
            raise ProtocolError(message)


def _validate_session_turns(session: ObservedSession) -> None:
    """Validate the same identity and state contract for active and latest turns.

    For example, metadata may omit every turn but cannot contain an empty ID.

    Raises
    ------
    ProtocolError
        If any supplied turn has an unknown state or empty identity.
    """
    turns = (*session.active_turns, session.latest_turn)
    if any(turn is not None and _has_invalid_turn(turn) for turn in turns):
        message = "Turn projection has an invalid state or identity."
        raise ProtocolError(message)


def _has_invalid_turn(turn: Turn) -> bool:
    """Check one active/latest turn against the shared protocol vocabulary.

    For example, a turn with an empty ``user_turn_id`` is invalid.

    Returns
    -------
    bool
        Whether the turn has an unsupported state or empty identity.
    """
    return turn.state not in TURN_STATES or not turn.user_turn_id


_EVENT_VALIDATORS = {
    "snapshot": _validate_session,
    "session.changed": _validate_session,
    "turn.started": _validate_turn_event,
    "turn.finished": _validate_turn_event,
}
