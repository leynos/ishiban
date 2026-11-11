"""Collector lifecycle writes recover without using an unconfirmed generation."""

import asyncio
import sqlite3
import types
import typing as typ
from unittest import mock

import pytest
import storage_support
from sqlalchemy.exc import OperationalError
from test_collector_storage_recovery import RefreshClock

from ishiban import collector as observation
from ishiban.task_ownership import cancel_and_reap

if typ.TYPE_CHECKING:
    import pathlib

    from ishiban.protocol import Catalogue
    from ishiban.storage import Store


class GenerationFault:
    """Fail one generation write, optionally continuing after a lost ACK."""

    def __init__(
        self,
        store: Store,
        *,
        fail_on: int,
        commit_before_failure: bool,
        keep_failing: bool = False,
    ) -> None:
        """Capture the real writer before the test replaces its boundary."""
        self.original = store.begin_generation
        self.fail_on = fail_on
        self.commit_before_failure = commit_before_failure
        self.keep_failing = keep_failing
        self.calls = 0

    async def begin(self) -> int:
        """Return only a later acknowledged generation after the fault.

        Returns
        -------
        int
            The store's acknowledged generation.

        Raises
        ------
        OperationalError
            On the selected write and optionally every later attempt.
        """
        self.calls += 1
        should_fail = self.calls == self.fail_on or (
            self.keep_failing and self.calls > self.fail_on
        )
        if should_fail:
            if self.calls == self.fail_on and self.commit_before_failure:
                await self.original()
            raise OperationalError("write", {}, sqlite3.OperationalError())
        return await self.original()


class DisconnectedHealthFault:
    """Fail a selected count of disconnect writes at the real store boundary."""

    def __init__(self, store: Store, *, fail_limit: int | None) -> None:
        """Keep the store writer for recovered and stopped health writes."""
        self.original = store.health
        self.fail_limit = fail_limit
        self.calls = 0

    async def health(
        self, state: str, generation: int, error: str | None = None
    ) -> int:
        """Forward other health writes and fault selected disconnect writes.

        Returns
        -------
        int
            The committed cursor after recovery.

        Raises
        ------
        OperationalError
            During the configured disconnect fault.
        """
        if state == "disconnected":
            self.calls += 1
            if self.fail_limit is None or self.calls <= self.fail_limit:
                raise OperationalError("write", {}, sqlite3.OperationalError())
        return await self.original(state, generation, error)


async def _cancel_after_cap(clock: RefreshClock, task: asyncio.Task[None]) -> None:
    """Advance six retry waits, hold the seventh, then reap cancellation."""
    try:
        async with asyncio.timeout(3):
            releases: list[asyncio.Event] = []
            for _ in range(7):
                release = await clock.retries.get()
                releases.append(release)
                if len(releases) < 7:
                    release.set()
        assert clock.retry_delays == [1, 2, 4, 8, 16, 30, 30], (
            "Lifecycle retry must use bounded exponential delays."
        )
        assert not task.done(), "Storage failure must retain task ownership."
    finally:
        if not task.done():
            task.cancel()
        outcome = await asyncio.wait_for(
            asyncio.gather(task, return_exceptions=True), timeout=2
        )
    assert isinstance(outcome[0], asyncio.CancelledError), (
        "Failed lifecycle writes must not replace caller cancellation."
    )


async def _advance(_delay: float) -> None:
    """Yield across collector retry and reconnect waits without wall-clock delay."""
    await asyncio.sleep(0)


async def _run_until_cancelled(
    collector: observation.Collector, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run a controlled source sequence through its expected cancellation."""
    monkeypatch.setattr(observation, "asyncio", types.SimpleNamespace(sleep=_advance))
    with pytest.raises(asyncio.CancelledError):
        await collector.run()


@pytest.mark.parametrize("reconnect", [False, True])
@pytest.mark.parametrize("commit_before_failure", [False, True])
@pytest.mark.asyncio
async def test_generation_fault_never_starts_observer_under_uncertain_generation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reconnect: bool,
    commit_before_failure: bool,
) -> None:
    """Initial and reconnect writes use only acknowledged source generations."""
    async with storage_support.opened_store(tmp_path) as store:
        fault = GenerationFault(
            store,
            fail_on=2 if reconnect else 1,
            commit_before_failure=commit_before_failure,
        )
        monkeypatch.setattr(store, "begin_generation", fault.begin)
        collector = observation.Collector(store, "leynos", github=False)
        seen: list[int] = []

        async def follow(_initial: Catalogue | None = None) -> None:
            """Disconnect once if requested, then commit one unique source event.

            Raises
            ------
            OSError
                The first observer disconnects in the reconnect scenario.
            asyncio.CancelledError
                The acknowledged observer ends the bounded test.
            """
            seen.append(collector.generation)
            if reconnect and len(seen) == 1:
                raise OSError
            event = storage_support.envelope(
                1,
                options=storage_support.EventOptions(
                    session=storage_support.observed_session()
                ),
            )
            await store.ingest(event, collector.generation)
            raise asyncio.CancelledError

        monkeypatch.setattr(collector, "_follow", follow)
        await _run_until_cancelled(collector, monkeypatch)
        expected = 1 + int(reconnect) + int(commit_before_failure)
        assert fault.calls == (3 if reconnect else 2), (
            "A failed generation start must be retried before observation."
        )
        assert seen == ([1, expected] if reconnect else [expected]), (
            "No observer may use a generation whose write was unacknowledged."
        )
        snapshot = storage_support.as_snapshot(await store.snapshot())
        assert snapshot["collector"]["generation"] == expected, (
            "Current health must reflect the acknowledged generation."
        )
        assert snapshot["collector"]["state"] == "stopped", (
            "Confirmed cancellation must persist stopped health."
        )
        assert snapshot["sessions"][0]["lastEvidenceGeneration"] == expected, (
            "The unique source event must use the acknowledged generation."
        )


@pytest.mark.asyncio
async def test_disconnected_health_recovery_precedes_reconnect(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient disconnect write fault cannot retire the observer loop."""
    async with storage_support.opened_store(tmp_path) as store:
        fault = DisconnectedHealthFault(store, fail_limit=1)
        monkeypatch.setattr(store, "health", fault.health)
        collector = observation.Collector(store, "leynos", github=False)
        follow = mock.AsyncMock(side_effect=[OSError(), asyncio.CancelledError()])
        monkeypatch.setattr(collector, "_follow", follow)
        await _run_until_cancelled(collector, monkeypatch)
        assert fault.calls == 2, "Disconnected health must retry the same write."
        assert follow.await_count == 2, (
            "Observer reconnects only after health recovers."
        )
        history = storage_support.as_events(await store.events(0))
        disconnected_count = sum(
            event["projection"].get("state") == "disconnected" for event in history
        )
        assert disconnected_count == 1, (
            "The recovered health transition must have one committed row."
        )


@pytest.mark.parametrize(
    "fault_site", ["generation", "generation-reconnect", "disconnected"]
)
@pytest.mark.asyncio
async def test_persistent_lifecycle_fault_caps_retry_and_preserves_cancellation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fault_site: str,
) -> None:
    """A capped wait cancels cleanly with accurate partial collector health."""
    clock = RefreshClock()
    monkeypatch.setattr(
        observation, "asyncio", types.SimpleNamespace(sleep=clock.sleep)
    )
    async with storage_support.opened_store(tmp_path) as store:
        if fault_site in {"generation", "generation-reconnect"}:
            fault: GenerationFault | DisconnectedHealthFault = GenerationFault(
                store,
                fail_on=2 if fault_site == "generation-reconnect" else 1,
                commit_before_failure=True,
                keep_failing=True,
            )
            monkeypatch.setattr(store, "begin_generation", fault.begin)
            follow = (
                mock.AsyncMock(side_effect=OSError())
                if fault_site == "generation-reconnect"
                else mock.AsyncMock()
            )
        else:
            fault = DisconnectedHealthFault(store, fail_limit=None)
            monkeypatch.setattr(store, "health", fault.health)
            follow = mock.AsyncMock(side_effect=OSError())
        collector = observation.Collector(store, "leynos", github=False)
        monkeypatch.setattr(collector, "_follow", follow)
        monkeypatch.setattr(observation.secrets, "randbelow", lambda _limit: 0)
        task = asyncio.create_task(collector.run())
        try:
            if fault_site == "generation-reconnect":
                async with asyncio.timeout(3):
                    reconnect_release = await clock.retries.get()
                assert clock.retry_delays == [1], (
                    "Source disconnect must wait before starting a new generation."
                )
                reconnect_release.set()
                clock.retry_delays.clear()
            await _cancel_after_cap(clock, task)
            expected_calls = 8 if fault_site == "generation-reconnect" else 7
            assert fault.calls == expected_calls, (
                "Every released backoff attempts the same lifecycle write."
            )
            assert follow.await_count == (0 if fault_site == "generation" else 1), (
                "No observer may run across the failed lifecycle boundary."
            )
            snapshot = storage_support.as_snapshot(await store.snapshot())
            expected_generation = 2 if fault_site == "generation-reconnect" else 1
            assert snapshot["collector"]["generation"] == expected_generation, (
                "The durable generation remains explicit after cancellation."
            )
            expected_state = "stopped" if fault_site == "disconnected" else "connecting"
            assert snapshot["collector"]["state"] == expected_state, (
                "Stopped health is skipped only while generation is unconfirmed."
            )
            if fault_site == "generation-reconnect":
                assert collector.generation == 1, (
                    "An unacknowledged reconnect retains the last confirmed generation."
                )
        finally:
            await cancel_and_reap((task,))
