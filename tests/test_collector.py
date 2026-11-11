"""A real fake-CLI boundary exercises catalogue and observer lifecycle together."""

import asyncio
import contextlib
import pathlib
import sys

import msgspec
import pytest
from lody_process_support import tracked_fake_lody_children
from storage_support import as_detail, as_events

from ishiban.collector import Collector
from ishiban.lody import read_catalogue
from ishiban.storage import Store
from ishiban.task_ownership import cancel_and_reap


class CollectorStatus(msgspec.Struct):
    """Only source health is relevant to this boundary assertion."""

    state: str


class SessionStatus(msgspec.Struct, rename="camel"):
    """A narrow semantic projection asserted after catalogue reconciliation."""

    repo_full_name: str | None
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
    assert transitions[0]["cursor"] <= session.last_event_id, (
        "Later catalogue metadata may advance the session cursor after live evidence."
    )
    assert transitions[0]["projection"]["title"] == "Observer activity transition", (
        "The observer payload must remain in its committed source event."
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
    monkeypatch: pytest.MonkeyPatch,
    observer_fixture: str | None,
    expected_state: str,
) -> None:
    """The observer path persists activity independently of catalogue metadata."""
    tail = (
        ""
        if observer_fixture is None
        else (pathlib.Path(__file__).parent / "fixtures" / observer_fixture).read_text()
    )
    executable = fake_lody(tmp_path, tail)
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'collector.sqlite3'}", "workspace")
    await store.initialize()
    async with contextlib.AsyncExitStack() as cleanup:
        cleanup.push_async_callback(store.close)
        children = await cleanup.enter_async_context(
            tracked_fake_lody_children(monkeypatch, executable)
        )
        initial = await read_catalogue("leynos", str(executable))
        collector = Collector(store, "leynos", executable=str(executable), github=False)
        task = asyncio.create_task(collector.run(initial))
        cleanup.push_async_callback(cancel_and_reap, (task,))
        async with asyncio.timeout(10):
            while True:
                current = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
                if current.collector.state == "following" and any(
                    session.state == expected_state
                    and session.repo_full_name == "leynos/fixture"
                    for session in current.sessions
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
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=9)
        final = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
        assert final.collector.state == "stopped", (
            "Cancellation must persist stopped health after reaping the child."
        )
        observer_children = [
            process for command, process in children if "observe" in command
        ]
        assert len(observer_children) == 1, (
            "The collector must own one native observer child."
        )
        assert observer_children[0].returncode is not None, (
            "Collector cancellation must terminate the native observer child."
        )
        assert (
            await asyncio.wait_for(observer_children[0].wait(), timeout=1)
            == observer_children[0].returncode
        ), "Collector cancellation must reap the observer before stopping."
