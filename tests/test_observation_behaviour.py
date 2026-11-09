"""Behavioural coverage for provenance across collector generations."""

import asyncio
import dataclasses as dc
import typing as typ

import msgspec
import pytest
from pytest_bdd import given, scenarios, then, when

from ishiban.domain import Envelope, ObservedSession, Turn
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

scenarios("features/observation.feature")


@dc.dataclass(slots=True)
class Runtime:
    """One synchronous BDD scenario owns one asynchronous database loop."""

    runner: asyncio.Runner
    store: Store
    generation: int = 0


class PublicSession(msgspec.Struct, rename="camel"):
    """Read only the evidence fields asserted by this scenario."""

    latest_turn: Turn
    last_evidence_generation: int


class PublicSnapshot(msgspec.Struct):
    """The scenario's narrow observable snapshot boundary."""

    sessions: list[PublicSession]


@pytest.fixture
def runtime(tmp_path: pathlib.Path) -> cabc.Iterator[Runtime]:
    """Own a temporary journal for one scenario.

    Yields
    ------
    Runtime
        A runner and its independent SQLite store.
    """
    with asyncio.Runner() as runner:
        store = Store(f"sqlite+aiosqlite:///{tmp_path / 'bdd.sqlite3'}", "workspace")
        runner.run(store.initialize())
        yield Runtime(runner, store)
        runner.run(store.close())


@given("a fresh observation journal")
def fresh_journal(runtime: Runtime) -> None:
    """Start the first collector generation."""
    runtime.generation = runtime.runner.run(runtime.store.begin_generation())


@when("a persisted completion is followed by a metadata-only restart")
def reconcile_restart(runtime: Runtime) -> None:
    """Feed genuine persisted evidence before a fresh metadata-only baseline."""
    completed = ObservedSession(
        session_id="session",
        machine_id="machine",
        state="idle",
        source="persisted",
        freshness="synced",
        latest_turn=Turn(user_turn_id="turn", state="completed"),
    )
    first = Envelope(
        version=1,
        stream_id="first",
        sequence=1,
        observed_at=1,
        workspace_id="workspace",
        type="snapshot",
        session_id="session",
        session=completed,
    )
    runtime.runner.run(runtime.store.ingest(first, runtime.generation))
    runtime.runner.run(runtime.store.begin_generation())
    metadata = ObservedSession(
        session_id="session", machine_id="machine", source="metadata"
    )
    second = Envelope(
        version=1,
        stream_id="second",
        sequence=1,
        observed_at=2,
        workspace_id="workspace",
        type="snapshot",
        session_id="session",
        session=metadata,
    )
    runtime.runner.run(runtime.store.ingest(second, runtime.generation + 1))


@then("the completion is retained as evidence from the earlier generation")
def retained_completion(runtime: Runtime) -> None:
    """Assert the materialized public boundary rather than database internals."""
    raw = runtime.runner.run(runtime.store.snapshot())
    snapshot = msgspec.convert(raw, type=PublicSnapshot)
    assert snapshot.sessions[0].latest_turn.state == "completed", (
        "Metadata after restart must retain the proven completion."
    )
    assert snapshot.sessions[0].last_evidence_generation == runtime.generation, (
        "Metadata cannot advance the durable evidence generation."
    )
