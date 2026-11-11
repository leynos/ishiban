"""A transient journal write must not retire the collector's refresh task."""

import asyncio
import contextlib
import dataclasses as dc
import sqlite3
import types
import typing as typ
from unittest import mock

import pytest
from sqlalchemy.exc import OperationalError
from storage_support import as_events, as_snapshot, observer_frame, opened_store

from ishiban import collector as observation
from ishiban.protocol import Catalogue, RawSession
from ishiban.task_ownership import cancel_and_reap

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.domain import CatalogueEntry
    from ishiban.storage import Store
    from tests.storage_contracts import Snapshot


@dc.dataclass(slots=True)
class RefreshClock:
    """Expose owned periodic and retry waits without patching global asyncio."""

    periodic: asyncio.Queue[asyncio.Event] = dc.field(default_factory=asyncio.Queue)
    retries: asyncio.Queue[asyncio.Event] = dc.field(default_factory=asyncio.Queue)
    retry_delays: list[float] = dc.field(default_factory=list)

    async def sleep(self, delay: float) -> None:
        """Hold a refresh boundary until the scenario explicitly advances it."""
        release = asyncio.Event()
        if delay == 300:
            self.periodic.put_nowait(release)
        else:
            self.retry_delays.append(delay)
            self.retries.put_nowait(release)
        await release.wait()


class OneTimeWriteFault:
    """Fail one catalogue or two health writes after the scenario arms it."""

    def __init__(self, store: Store, site: str) -> None:
        """Keep the original writer so all successful calls remain real SQL."""
        self.original_catalogue = store.catalogue
        self.original_health = store.health
        self.site = site
        self.armed = False
        self.remaining = 1 if site == "catalogue" else 2

    def arm(self) -> None:
        """Start the one-shot fault at the selected initial or periodic boundary."""
        self.armed = True

    def should_fail(self, site: str) -> bool:
        """Consume only failures at the selected write site.

        Returns
        -------
        bool
            Whether this call is the next injected storage failure.
        """
        if not self.armed or self.site != site:
            return False
        if self.remaining == 0:
            return False
        self.remaining -= 1
        return True

    async def catalogue(self, entry: CatalogueEntry, generation: int) -> int | None:
        """Write a real catalogue row except for one injected lock failure.

        Returns
        -------
        int or None
            The real store's cursor or unchanged result.

        Raises
        ------
        OperationalError
            On the selected one-time catalogue fault.
        """
        if self.should_fail("catalogue"):
            raise OperationalError("catalogue", {}, sqlite3.OperationalError("locked"))
        return await self.original_catalogue(entry, generation)

    async def health(
        self, state: str, generation: int, error: str | None = None
    ) -> int:
        """Fail the main and warning health writes once, then delegate.

        Returns
        -------
        int
            The real store's committed health cursor.

        Raises
        ------
        OperationalError
            On the two selected health-write faults.
        """
        if self.should_fail("health"):
            raise OperationalError("health", {}, sqlite3.OperationalError("locked"))
        return await self.original_health(state, generation, error)


def catalogue(title: str) -> Catalogue:
    """Supply one changed session association for a refresh.

    Returns
    -------
    Catalogue
        One workspace-bound session with the requested title.
    """
    return Catalogue(
        ok=True,
        workspace_id="w1",
        sessions=[
            RawSession(id="session", title=title, repo_full_name="leynos/fixture")
        ],
    )


async def wait_for_snapshot(
    store: Store, predicate: cabc.Callable[[Snapshot], bool]
) -> Snapshot:
    """Wait for committed journal evidence rather than a guessed task delay.

    Returns
    -------
    Snapshot
        The first public snapshot satisfying the scenario's condition.

    """
    async with asyncio.timeout(2):
        while True:
            snapshot = as_snapshot(await store.snapshot())
            if predicate(snapshot):
                return snapshot
            await asyncio.sleep(0.01)


async def assert_initial_order(store: Store) -> None:
    """Require all bootstrap catalogue rows before the first following event."""
    events = as_events(await store.events(0))
    first_following = next(
        index
        for index, event in enumerate(events)
        if event["projection"].get("state") == "following"
    )
    assert any(
        event["source"] == "lody.catalogue" for event in events[:first_following]
    ), "Recovery must journal metadata before following health."
    assert all(
        event["source"] != "lody.catalogue" for event in events[first_following:]
    ), "Initial metadata must stay inside the quiet phase."


async def assert_retry_state(
    store: Store, phase: str, site: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Check phase-preserving warnings before the blocked retry resumes."""
    blocked = as_snapshot(await store.snapshot())
    expected_state = "catalogue_ready" if phase == "initial" else "following"
    assert blocked["collector"]["state"] == expected_state, (
        "A retry must preserve the quiet initial or active periodic phase."
    )
    if site == "catalogue":
        assert "storage" in str(blocked["collector"]["lastError"]).lower(), (
            "A writable store must publish its storage diagnostic."
        )
    else:
        assert "warning could not be persisted" in caplog.text, (
            "An unavailable diagnostic write must be reported safely."
        )
        assert "locked" not in caplog.text, "Private storage errors must not leak."
    if phase == "initial":
        assert not any(
            event["projection"].get("state") == "following"
            for event in as_events(await store.events(0))
        ), "Initial retry must keep following health after metadata."


def first_session_value(
    frame: Snapshot, field: typ.Literal["state", "title"]
) -> str | None:
    """Read one projected field only when the observer has a session.

    Returns
    -------
    str or None
        The first session's requested field, if it has been projected.
    """
    return frame["sessions"][0].get(field) if frame["sessions"] else None


@dc.dataclass(slots=True)
class RecoveryCase:
    """Carry one collector retry's evidence and controlled boundaries."""

    phase: str
    site: str
    store: Store
    clock: RefreshClock
    stdout: asyncio.StreamReader
    catalogue_read: mock.AsyncMock
    caplog: pytest.LogCaptureFixture
    fault: OneTimeWriteFault
    task: asyncio.Task[None]

    async def await_blocked_retry(self) -> asyncio.Event:
        """Reach the injected fault and prove observation stays live.

        Returns
        -------
        asyncio.Event
            The held backoff gate to release for recovery.
        """
        if self.phase == "periodic":
            await wait_for_snapshot(
                self.store,
                lambda frame: frame["collector"]["state"] == "following",
            )
            self.fault.arm()
            (await asyncio.wait_for(self.clock.periodic.get(), 2)).set()
        retry_release = await asyncio.wait_for(self.clock.retries.get(), 2)
        await assert_retry_state(self.store, self.phase, self.site, self.caplog)
        self.stdout.feed_data(observer_frame("lody-observer-activity.jsonl"))
        await wait_for_snapshot(
            self.store, lambda frame: first_session_value(frame, "state") == "running"
        )
        assert self.clock.retry_delays == [1.0], "The first storage retry must wait."
        return retry_release

    async def assert_recovered_and_later_refresh(
        self, retry_release: asyncio.Event
    ) -> None:
        """Require cleared health, then a distinct later periodic catalogue update."""
        retry_release.set()
        expected_title = "Initial title" if self.phase == "initial" else "Updated title"
        await wait_for_snapshot(
            self.store,
            lambda frame: (
                frame["collector"]["state"] == "following"
                and frame["collector"]["lastError"] is None
                and first_session_value(frame, "title") == expected_title
            ),
        )
        assert not self.task.done(), "A recovered observer must remain attached."
        if self.phase == "initial":
            await assert_initial_order(self.store)
            self.catalogue_read.assert_not_awaited()
        (await asyncio.wait_for(self.clock.periodic.get(), 2)).set()
        await wait_for_snapshot(
            self.store,
            lambda frame: first_session_value(frame, "title") == "Later title",
        )
        assert not self.task.done(), "The next periodic refresh must still be owned."
        assert self.catalogue_read.await_count == (
            1 if self.phase == "initial" else 3
        ), "Recovery must retain the initial catalogue and resume periodic reads."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ("initial", "catalogue"),
        ("initial", "health"),
        ("periodic", "catalogue"),
        ("periodic", "health"),
    ],
)
async def test_storage_write_recovery_keeps_observer_and_later_refresh(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: tuple[str, str],
) -> None:
    """Retry a failed write, then accept another real periodic catalogue change."""
    failure_phase, fault_site = failure
    stdout = asyncio.StreamReader()
    stdout.feed_data(observer_frame("lody-observer.jsonl"))

    @contextlib.asynccontextmanager
    async def source(
        _command: tuple[str, ...],
    ) -> cabc.AsyncIterator[types.SimpleNamespace]:
        """Yield the controlled observer stream until the collector is cancelled.

        Yields
        ------
        types.SimpleNamespace
            The owned observer's stdout boundary.
        """
        yield types.SimpleNamespace(stdout=stdout)

    clock = RefreshClock()
    monkeypatch.setattr(observation, "child", source)
    monkeypatch.setattr(
        observation,
        "asyncio",
        types.SimpleNamespace(sleep=clock.sleep, create_task=asyncio.create_task),
    )
    reads = (
        [catalogue("Later title")]
        if failure_phase == "initial"
        else [
            catalogue("Updated title"),
            catalogue("Updated title"),
            catalogue("Later title"),
        ]
    )
    catalogue_read = mock.AsyncMock(side_effect=reads)
    monkeypatch.setattr(observation, "read_catalogue", catalogue_read)

    async with opened_store(tmp_path) as store:
        fault = OneTimeWriteFault(store, fault_site)
        monkeypatch.setattr(store, "catalogue", fault.catalogue)
        monkeypatch.setattr(store, "health", fault.health)
        if failure_phase == "initial":
            fault.arm()
        task = asyncio.create_task(
            observation.Collector(store, "leynos", github=False).run(
                catalogue("Initial title")
            )
        )
        try:
            case = RecoveryCase(
                failure_phase,
                fault_site,
                store,
                clock,
                stdout,
                catalogue_read,
                caplog,
                fault,
                task,
            )
            retry_release = await case.await_blocked_retry()
            await case.assert_recovered_and_later_refresh(retry_release)
        finally:
            await cancel_and_reap((task,))


@pytest.mark.asyncio
async def test_persistent_storage_failure_uses_capped_backoff_and_cancels(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable store stays observable without a busy retry loop."""
    clock = RefreshClock()
    monkeypatch.setattr(
        observation, "asyncio", types.SimpleNamespace(sleep=clock.sleep)
    )
    async with opened_store(tmp_path) as store:
        failed_write = mock.AsyncMock(
            side_effect=OperationalError(
                "catalogue", {}, sqlite3.OperationalError("locked")
            )
        )
        monkeypatch.setattr(store, "catalogue", failed_write)
        collector = observation.Collector(store, "leynos", github=False)
        collector.generation = await store.begin_generation()
        task = asyncio.create_task(
            collector._refresh(catalogue("Initial title"), start_immediately=True)
        )
        try:
            async with asyncio.timeout(3):
                for attempt, expected_delay in enumerate((1, 2, 4, 8, 16, 30, 30)):
                    release = await clock.retries.get()
                    assert clock.retry_delays[-1] == expected_delay, (
                        "Storage retry delays must grow only to the fixed cap."
                    )
                    assert not task.done(), (
                        "A retryable fault must retain task ownership."
                    )
                    if attempt < 6:
                        release.set()
            assert failed_write.await_count == 7, (
                "Each retry needs one new write attempt."
            )
        finally:
            await cancel_and_reap((task,))
        assert task.cancelled(), "Cancellation must reap the blocked refresh task."
