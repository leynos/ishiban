"""Mixed observer records cannot consume stream position when validation fails."""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from test_protocol import event_line

from ishiban.protocol import ProtocolError, StreamPosition, decode_event

VALID_TYPES = (
    "ready",
    "snapshot",
    "session.changed",
    "turn.started",
    "turn.finished",
    "session.removed",
)
INVALID_KINDS = (
    "wrong-version",
    "foreign-workspace",
    "empty-stream",
    "changed-stream",
    "duplicate-sequence",
    "gapped-sequence",
    "negative-timestamp",
    "oversized-timestamp",
    "unknown-type",
    "missing-session-id",
    "mismatched-session",
    "invalid-session-state",
    "invalid-active-turn",
    "missing-turn-id",
    "missing-turn-outcome",
    "malformed-json",
)
INVALID_FIELDS: dict[str, dict[str, object]] = {
    "wrong-version": {"version": 2},
    "foreign-workspace": {"workspaceId": "foreign"},
    "empty-stream": {"streamId": ""},
    "negative-timestamp": {"observedAt": -1},
    "oversized-timestamp": {"observedAt": 8_640_000_000_000_001},
    "unknown-type": {"type": "error"},
    "missing-session-id": {"type": "session.removed"},
    "missing-turn-id": {"type": "turn.started", "sessionId": "s1"},
    "missing-turn-outcome": {
        "type": "turn.finished",
        "sessionId": "s1",
        "userTurnId": "u1",
    },
}
INVALID_SESSIONS: dict[str, dict[str, object]] = {
    "mismatched-session": {"sessionId": "other"},
    "invalid-session-state": {"sessionId": "s1", "state": "broken"},
    "invalid-active-turn": {
        "sessionId": "s1",
        "activeTurns": [{"userTurnId": "", "state": "running"}],
    },
}


def _valid_line(kind: str, sequence: int) -> bytes:
    """Build a recognized record after the model's next accepted sequence.

    For example, a turn finish names a stable turn and a terminal outcome.

    Returns
    -------
    bytes
        One valid encoded observer record in the fixed workspace and stream.
    """
    fields: dict[str, object] = {"type": kind, "sequence": sequence}
    match kind:
        case "snapshot" | "session.changed":
            fields.update({
                "sessionId": "s1",
                "session": {"sessionId": "s1", "state": "unknown"},
            })
        case "turn.started":
            fields.update({"sessionId": "s1", "userTurnId": "u1"})
        case "turn.finished":
            fields.update({
                "sessionId": "s1",
                "userTurnId": "u1",
                "outcome": "completed",
            })
        case "session.removed":
            fields["sessionId"] = "s1"
    return event_line(**fields)


def _invalid_line(kind: str, sequence: int, *, has_stream: bool) -> bytes:
    """Perturb one otherwise valid next record at a named trust boundary.

    For example, a changed stream is invalid only after an accepted prefix.

    Returns
    -------
    bytes
        An encoded record rejected without consuming the expected sequence.
    """
    match kind:
        case "malformed-json":
            return b"{"
        case "changed-stream":
            return event_line(sequence=sequence, streamId="other" if has_stream else "")
        case "duplicate-sequence":
            return event_line(sequence=sequence - 1)
        case "gapped-sequence":
            return event_line(sequence=sequence + 1)
        case _ if kind in INVALID_SESSIONS:
            return event_line(
                type="snapshot",
                sequence=sequence,
                sessionId="s1",
                session=INVALID_SESSIONS[kind],
            )
        case _:
            return event_line(sequence=sequence, **INVALID_FIELDS[kind])


def _accept_record(position: StreamPosition, kind: str, sequence: int) -> None:
    """Check one known-valid record against the independent accepted count."""
    event = decode_event(_valid_line(kind, sequence), "workspace", position)
    assert event.type == kind, "The accepted event must retain its valid kind."
    assert (position.stream_id, position.sequence) == ("stream", sequence), (
        "Every valid record must advance exactly once."
    )


@example(prefix=[], faults=[("changed-stream", "ready")])
@example(
    prefix=["snapshot", "turn.started", "turn.finished"],
    faults=[
        ("changed-stream", "session.changed"),
        ("mismatched-session", "turn.started"),
        ("duplicate-sequence", "ready"),
    ],
)
@given(
    prefix=st.lists(st.sampled_from(VALID_TYPES), min_size=0, max_size=12),
    faults=st.lists(
        st.tuples(st.sampled_from(INVALID_KINDS), st.sampled_from(VALID_TYPES)),
        min_size=1,
        max_size=6,
    ),
)
@settings(max_examples=60, deadline=None)
def test_rejected_observer_records_leave_mixed_stream_prefix_recoverable(
    prefix: list[str], faults: list[tuple[str, str]]
) -> None:
    """Every rejected record leaves both position fields intact for recovery."""
    position = StreamPosition()
    accepted_sequence = 0
    expected_stream: str | None = None
    for kind in prefix:
        accepted_sequence += 1
        _accept_record(position, kind, accepted_sequence)
        expected_stream = "stream"

    for invalid_kind, recovery_kind in faults:
        rejected = _invalid_line(
            invalid_kind, accepted_sequence + 1, has_stream=expected_stream is not None
        )
        with pytest.raises(ProtocolError):
            decode_event(rejected, "workspace", position)
        assert (position.stream_id, position.sequence) == (
            expected_stream,
            accepted_sequence,
        ), f"Rejected {invalid_kind} must leave both position fields unchanged."
        accepted_sequence += 1
        _accept_record(position, recovery_kind, accepted_sequence)
        expected_stream = "stream"
