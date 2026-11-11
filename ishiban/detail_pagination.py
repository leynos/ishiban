"""Encode bounded session-turn page positions without granting authority."""

import base64
import binascii
import hashlib
import re

import msgspec

TURN_PAGE_SIZE = 100
TURN_CURSOR_VERSION = 2
MAX_TURN_CURSOR_LENGTH = 256
MAX_EVENT_ID = 9_223_372_036_854_775_807
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class InvalidTurnCursorError(ValueError):
    """Reject an invalid turn continuation without echoing its contents."""

    def __init__(self) -> None:
        """Create a safe API error; for example, ``str(error)`` is generic."""
        super().__init__("Invalid turn cursor.")


class TurnPageCursor(msgspec.Struct, rename="camel", frozen=True):
    """Bind a fixed-size turn-group rank to its workspace and session."""

    version: int
    scope_digest: str
    last_event_id: int
    rank: int


def cursor_scope_digest(workspace_id: str, session_id: str) -> str:
    """Hash a structured identity so different field splits stay distinct.

    For example, ``('ab', 'c')`` differs from ``('a', 'bc')``.

    Returns
    -------
    str
        A fixed-width lowercase SHA256 digest of both identifiers.
    """
    return hashlib.sha256(msgspec.json.encode((workspace_id, session_id))).hexdigest()


def encode_turn_cursor(cursor: TurnPageCursor) -> str:
    """Encode a continuation; for example, rank 100 follows rank 99.

    Returns
    -------
    str
        A URL-safe position token for the next detail request.
    """
    return base64.urlsafe_b64encode(msgspec.json.encode(cursor)).rstrip(b"=").decode()


def parse_turn_cursor(
    token: str | None, workspace_id: str, session_id: str
) -> TurnPageCursor | None:
    """Validate a page position for one session, or select its first page.

    For example, a token issued for another session raises
    ``InvalidTurnCursorError``.

    Returns
    -------
    TurnPageCursor or None
        A validated continuation, or ``None`` for the first page.

    Raises
    ------
    InvalidTurnCursorError
        If the token is malformed, oversized or bound to another identity.
    """
    if token is None:
        return None
    if len(token) > MAX_TURN_CURSOR_LENGTH or _TOKEN.fullmatch(token) is None:
        raise InvalidTurnCursorError
    try:
        data = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
        cursor = msgspec.json.decode(data, type=TurnPageCursor)
    except (binascii.Error, msgspec.DecodeError, msgspec.ValidationError) as exc:
        raise InvalidTurnCursorError from exc
    _validate_cursor_identity(cursor, workspace_id, session_id)
    _validate_cursor_position(cursor, token)
    return cursor


def _validate_cursor_identity(
    cursor: TurnPageCursor, workspace_id: str, session_id: str
) -> None:
    """Reject a continuation bound to another session or protocol version.

    For example, a cursor from another workspace raises
    ``InvalidTurnCursorError``.

    Raises
    ------
    InvalidTurnCursorError
        If the version, workspace or session does not match.
    """
    if cursor.version != TURN_CURSOR_VERSION:
        raise InvalidTurnCursorError
    if cursor.scope_digest != cursor_scope_digest(workspace_id, session_id):
        raise InvalidTurnCursorError
    if _DIGEST.fullmatch(cursor.scope_digest) is None:
        raise InvalidTurnCursorError


def _validate_cursor_position(cursor: TurnPageCursor, token: str) -> None:
    """Reject an invalid keyset position or noncanonical encoded token.

    For example, a negative event ID cannot identify a retained turn.

    Raises
    ------
    InvalidTurnCursorError
        If the turn identity, event position or encoding is invalid.
    """
    if not 0 < cursor.last_event_id <= MAX_EVENT_ID:
        raise InvalidTurnCursorError
    if not 0 < cursor.rank <= MAX_EVENT_ID:
        raise InvalidTurnCursorError
    if encode_turn_cursor(cursor) != token:
        raise InvalidTurnCursorError
