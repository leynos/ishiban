"""Encode bounded session-turn page positions without granting authority."""

import base64
import binascii
import re

import msgspec

TURN_PAGE_SIZE = 100
MAX_TURN_CURSOR_LENGTH = 4096
MAX_EVENT_ID = 9_223_372_036_854_775_807
MAX_TURN_ID_LENGTH = 255
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,4096}\Z")


class InvalidTurnCursorError(ValueError):
    """Reject an invalid turn continuation without echoing its contents."""

    def __init__(self) -> None:
        """Create a safe API error; for example, ``str(error)`` is generic."""
        super().__init__("Invalid turn cursor.")


class TurnPageCursor(msgspec.Struct, rename="camel", frozen=True):
    """Bind a turn position to its workspace and session identity."""

    version: int
    workspace_id: str
    session_id: str
    last_event_id: int
    user_turn_id: str


def encode_turn_cursor(cursor: TurnPageCursor) -> str:
    """Encode a continuation; for example, ``u100`` follows ``u099``.

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
    _validate_turn_cursor(cursor, token, workspace_id, session_id)
    return cursor


def _validate_turn_cursor(
    cursor: TurnPageCursor, token: str, workspace_id: str, session_id: str
) -> None:
    """Reject a cursor whose decoded position or identity is invalid.

    For example, a cursor from another workspace raises
    ``InvalidTurnCursorError``.

    Raises
    ------
    InvalidTurnCursorError
        If the cursor position or identity is invalid.
    """
    if cursor.version != 1 or cursor.workspace_id != workspace_id:
        raise InvalidTurnCursorError
    if cursor.session_id != session_id or not cursor.user_turn_id:
        raise InvalidTurnCursorError
    if len(cursor.user_turn_id) > MAX_TURN_ID_LENGTH:
        raise InvalidTurnCursorError
    if not 0 < cursor.last_event_id <= MAX_EVENT_ID:
        raise InvalidTurnCursorError
    if encode_turn_cursor(cursor) != token:
        raise InvalidTurnCursorError
