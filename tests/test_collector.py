"""A real fake-CLI boundary exercises catalogue and observer lifecycle together."""

import asyncio
import pathlib
import sys

import msgspec
import pytest
from storage_support import as_detail, as_events

from ishiban.collector import Collector
from ishiban.lody import read_catalogue
from ishiban.storage import Store


class CollectorStatus(msgspec.Struct):
    """Only source health is relevant to this boundary assertion."""

    state: str


class SessionStatus(msgspec.Struct, rename="camel"):
    """A narrow semantic projection asserted after catalogue reconciliation."""

    repo_full_name: str
    stage: str
    state: str
    title: str
    last_event_id: int


class SnapshotStatus(msgspec.Struct):
    """Typed public response without incidental timestamps or host identifiers."""

    collector: CollectorStatus
    sessions: list[SessionStatus]


def fake_lody(directory: pathlib.Path, observer_tail: str = "") -> pathlib.Path:
    """Write a hanging fake CLI from the non-secret fixture corpus.

    Returns
    -------
    pathlib.Path
        Executable that emits one complete response before lingering.
    """
    fixtures = pathlib.Path(__file__).parent / "fixtures"
    catalogue = (fixtures / "lody-catalogue.json").read_text()
    events = (fixtures / "lody-observer.jsonl").read_text() + observer_tail
    executable = directory / "fake-lody"
    executable.write_text(
        f"#!{sys.executable}\nimport sys, time\n"
        f"catalogue = {catalogue!r}\nevents = {events!r}\n"
        "print(catalogue if 'list' in sys.argv else events, end='', flush=True)\n"
        "time.sleep(120)\n"
    )
    executable.chmod(0o700)
    return executable


async def assert_observer_transition(store: Store, session: SessionStatus) -> None:
    """Check this collector fixture's source event and corresponding projection."""
    history = as_events(await store.events(after=0))
    transitions = [
        event
        for event in history
        if event["source"] == "lody.observe"
        and event["projection"].get("state") == "running"
    ]
    assert len(transitions) == 1, (
        "The observer activity transition must have one durable journal row."
    )
    assert transitions[0]["cursor"] == session.last_event_id, (
        "The running projection must point to its committed observer event."
    )
    assert session.title == "Observer activity transition", (
        "The observer payload must survive ingestion rather than catalogue replacement."
    )
    detail = as_detail(await store.detail("session"))
    assert detail is not None, "The observed session must retain its journal detail."
    assert any(
        event["eventType"] == "session.changed" and event["observedAt"] == 2
        for event in detail["recentEvents"]
    ), "The source journal must retain the distinct observer event."


@pytest.mark.parametrize(
    ("observer_fixture", "expected_state"),
    [(None, "unknown"), ("lody-observer-activity.jsonl", "running")],
    ids=["metadata-baseline", "observer-activity-transition"],
)
@pytest.mark.asyncio
async def test_collector_ingests_observer_and_reaps_it_on_cancellation(
    tmp_path: pathlib.Path,
    observer_fixture: str | None,
    expected_state: str,
) -> None:
    """The observer path persists activity independently of catalogue metadata."""
    fixtures = pathlib.Path(__file__).parent / "fixtures"
    tail = "" if observer_fixture is None else (fixtures / observer_fixture).read_text()
    executable = fake_lody(tmp_path, tail)
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'collector.sqlite3'}", "workspace")
    await store.initialize()
    initial = await read_catalogue("leynos", str(executable))
    collector = Collector(store, "leynos", executable=str(executable), github=False)
    task = asyncio.create_task(collector.run(initial))
    try:
        async with asyncio.timeout(10):
            while True:
                current = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
                if (
                    current.collector.state == "following"
                    and current.sessions[0].state == expected_state
                ):
                    break
                await asyncio.sleep(0.01)
        assert current.sessions[0].repo_full_name == "leynos/fixture", (
            "Catalogue enrichment must retain the repository association."
        )
        assert current.sessions[0].stage == "planning", (
            "A successful empty PR association must classify as Planning."
        )
        assert current.sessions[0].state == expected_state, (
            "Only the distinct observer event may change catalogue-only activity."
        )
        if observer_fixture is not None:
            await assert_observer_transition(store, current.sessions[0])
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        final = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
        assert final.collector.state == "stopped", (
            "Cancellation must persist stopped health after reaping the child."
        )
        await store.close()
