"""Observer validation fails closed before a partial journal can be exposed."""

import msgspec
import pytest

from ishiban.protocol import (
    ProtocolError,
    StreamPosition,
    decode_catalogue,
    decode_event,
)


def event_line(**changes: object) -> bytes:
    """Build a valid ready record; for example, override its workspace identity.

    Returns
    -------
    bytes
        Encoded fixture envelope with the requested changes.
    """
    record = {
        "version": 1,
        "streamId": "stream",
        "sequence": 1,
        "observedAt": 1,
        "workspaceId": "workspace",
        "type": "ready",
    }
    record.update(changes)
    return msgspec.json.encode(record)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 2},
        {"workspaceId": "foreign"},
        {"sequence": 3},
        {"type": "error"},
        {"observedAt": -1},
    ],
)
def test_invalid_envelope_does_not_advance_position(changes: dict[str, object]) -> None:
    """Rejected messages cannot make a later event appear contiguous."""
    position = StreamPosition()
    with pytest.raises(ProtocolError):
        decode_event(event_line(**changes), "workspace", position)
    assert position.sequence == 0, (
        "Invalid input must leave the stream position unchanged."
    )


def test_stream_identity_cannot_change_within_a_child() -> None:
    """One process-local sequence belongs to one stream identity."""
    position = StreamPosition()
    decode_event(event_line(), "workspace", position)
    with pytest.raises(ProtocolError, match="identity changed"):
        decode_event(event_line(streamId="other", sequence=2), "workspace", position)


def test_incomplete_completion_is_rejected() -> None:
    """A terminal transition needs both turn identity and a known outcome."""
    with pytest.raises(ProtocolError):
        decode_event(
            event_line(type="turn.finished", sessionId="session", outcome="completed"),
            "workspace",
            StreamPosition(),
        )


def test_metadata_snapshot_can_omit_machine_identity() -> None:
    """The live CLI omits undefined machine IDs for one historical session."""
    line = event_line(
        type="snapshot",
        sessionId="session",
        session={
            "sessionId": "session",
            "archived": False,
            "state": "unknown",
            "source": "metadata",
            "freshness": "synced",
            "activeTurns": [],
        },
    )
    event = decode_event(line, "workspace", StreamPosition())
    assert event.session is not None, (
        "A metadata snapshot without a machine ID must still decode."
    )
    assert not event.session.machine_id, (
        "Missing machine identity must remain explicitly unknown."
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"sessionId": "another"},
        {"state": "broken"},
        {"source": "guessed"},
        {"freshness": "recent"},
        {"latestTurn": {"userTurnId": "turn", "state": "broken"}},
        {"activeTurns": [{"userTurnId": "", "state": "running"}]},
    ],
)
def test_invalid_session_fields_do_not_consume_a_stream_position(
    changes: dict[str, object],
) -> None:
    """Every session field family must validate before the stream advances."""
    session: dict[str, object] = {"sessionId": "session", **changes}
    position = StreamPosition()
    with pytest.raises(ProtocolError):
        decode_event(
            event_line(type="snapshot", sessionId="session", session=session),
            "workspace",
            position,
        )
    assert (position.stream_id, position.sequence) == (None, 0), (
        "Rejected session metadata or turns must not consume their envelope."
    )


@pytest.mark.parametrize("identities", [[""], ["session", "session"]])
def test_catalogue_rejects_missing_and_duplicate_session_ids(
    identities: list[str],
) -> None:
    """Catalogue reconciliation needs nonempty unique stable session identities."""
    data = msgspec.json.encode({
        "ok": True,
        "workspaceId": "workspace",
        "sessions": [{"id": identity} for identity in identities],
    })
    with pytest.raises(ProtocolError, match="missing or duplicate"):
        decode_catalogue(data)
