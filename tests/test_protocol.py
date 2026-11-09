"""Observer validation fails closed before a partial journal can be exposed."""

import msgspec
import pytest

from ishiban.protocol import ProtocolError, StreamPosition, decode_event


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
