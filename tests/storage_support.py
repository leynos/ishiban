"""Shared constructors for storage contract tests."""

import contextlib as ctx
import dataclasses as dc
import pathlib
import typing as typ

from ishiban.domain import Envelope, ObservedSession, Turn
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

    from tests.storage_contracts import Detail, Event, Snapshot


@dc.dataclass(frozen=True, slots=True)
class EventOptions:
    """Optional envelope data used by storage contract tests."""

    stream_id: str = "stream-1"
    event_type: str = "session.changed"
    session: ObservedSession | None = None
    user_turn_id: str | None = None
    assistant_turn_id: str | None = None
    outcome: str | None = None
    duration_ms: int | None = None


_DEFAULT_EVENT_OPTIONS = EventOptions()


def observer_frame(name: str) -> bytes:
    """Load a committed observer fixture for the isolated ``w1`` workspace.

    For example, ``observer_frame('lody-observer.jsonl')`` supplies the ready
    frame to a controlled collector stream.

    Returns
    -------
    bytes
        The fixture frame with its workspace identity adapted to ``w1``.
    """
    source = pathlib.Path(__file__).parent / "fixtures" / name
    return source.read_bytes().replace(
        b'"workspaceId":"workspace"', b'"workspaceId":"w1"'
    )


def as_snapshot(value: dict[str, object]) -> Snapshot:
    """Narrow the public snapshot for strongly typed test assertions.

    Returns
    -------
    Snapshot
        The same value narrowed to its tested public fields.
    """
    return typ.cast("Snapshot", value)


def as_events(value: list[dict[str, object]]) -> list[Event]:
    """Narrow replay payloads for cursor and projection assertions.

    Returns
    -------
    list[Event]
        The same event payloads narrowed to their tested fields.
    """
    return typ.cast("list[Event]", value)


def as_detail(value: dict[str, object] | None) -> Detail | None:
    """Narrow an optional detail record for typed contract assertions.

    Returns
    -------
    Detail or None
        The same detail record narrowed to its tested fields.
    """
    return typ.cast("Detail | None", value)


@ctx.asynccontextmanager
async def opened_store(directory: Path) -> cabc.AsyncIterator[Store]:
    """Yield an initialized store backed by a database in ``directory``.

    Yields
    ------
    Store
        A migrated store scoped to workspace ``w1``.
    """
    store = Store(f"sqlite+aiosqlite:///{directory / 'ishiban.sqlite3'}", "w1")
    await store.initialize()
    try:
        yield store
    finally:
        await store.close()


def observed_session(
    *,
    state: str = "running",
    source: str = "persisted",
    latest_turn: Turn | None = None,
    active_turns: list[Turn] | None = None,
) -> ObservedSession:
    """Build a compact session envelope for projection tests.

    Returns
    -------
    ObservedSession
        A session with test-stable identifiers and requested evidence.
    """
    return ObservedSession(
        session_id="s1",
        machine_id="m1",
        title="Compiler repair",
        archived=False,
        state=state,
        source=source,
        freshness="synced" if source == "persisted" else "unavailable",
        latest_turn=latest_turn,
        active_turns=active_turns if active_turns is not None else [],
    )


def envelope(
    sequence: int,
    *,
    options: EventOptions = _DEFAULT_EVENT_OPTIONS,
) -> Envelope:
    """Build a version-one event for one workspace and stream.

    Returns
    -------
    Envelope
        A validated event with the supplied sequence and optional fields.
    """
    return Envelope(
        version=1,
        stream_id=options.stream_id,
        sequence=sequence,
        observed_at=1_700_000_000_000 + sequence,
        workspace_id="w1",
        type=options.event_type,
        session_id="s1",
        session=options.session,
        user_turn_id=options.user_turn_id,
        assistant_turn_id=options.assistant_turn_id,
        outcome=options.outcome,
        duration_ms=options.duration_ms,
    )
