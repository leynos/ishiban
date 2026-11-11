"""Shape complete private session facts into bounded public turn previews."""

import hashlib
import typing as typ

import msgspec

ACTIVE_TURN_PREVIEW_LIMIT = 100


def _turn_fact(turn: dict[str, object]) -> bytes:
    """Encode meaningful turn facts; for example, omit observation timing.

    Returns
    -------
    bytes
        Stable JSON for the turn identity, state and optional error.
    """
    return msgspec.json.encode((
        turn.get("userTurnId"),
        turn.get("state"),
        turn.get("error"),
    ))


def public_session(projection: dict[str, object]) -> dict[str, object]:
    """Return a bounded response copy after any runtime cache overlay.

    For example, 101 private active turns become 100 preview turns and an
    exact count of 101, while the source projection remains complete.

    Returns
    -------
    dict[str, object]
        A public session with a stable full-set semantic revision.
    """
    turns = typ.cast("list[dict[str, object]]", projection.get("activeTurns", []))
    facts = sorted(_turn_fact(turn) for turn in turns)
    revision = hashlib.sha256(b"[" + b",".join(facts) + b"]").hexdigest()
    preview = sorted(
        turns, key=lambda turn: (_turn_fact(turn), msgspec.json.encode(turn))
    )[:ACTIVE_TURN_PREVIEW_LIMIT]
    return {
        **projection,
        "activeTurns": preview,
        "activeTurnCount": len(turns),
        "activeTurnsTruncated": len(turns) > ACTIVE_TURN_PREVIEW_LIMIT,
        "activeTurnsRevision": revision,
    }
