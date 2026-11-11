"""Collector startup must ingest live events while metadata enrichment waits."""

import asyncio
import contextlib
import functools
import typing as typ
from unittest import mock

import pytest
import storage_support

from ishiban import collector as observation
from ishiban.protocol import Catalogue, ProtocolError, RawPR, RawSession
from ishiban.task_ownership import cancel_and_reap

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.storage import Store
    from tests.storage_contracts import Snapshot


@contextlib.asynccontextmanager
async def _controlled_child(
    _command: tuple[str, ...], *, stdout: asyncio.StreamReader
) -> cabc.AsyncGenerator[mock.Mock]:
    """Expose one controlled observer stream through the existing child boundary.

    Yields
    ------
    mock.Mock
        Process with the supplied stdout stream.
    """
    yield mock.Mock(stdout=stdout)


async def _assert_bootstrap_order(store: Store) -> None:
    """Keep every initial catalogue row between ready and following health."""
    events = storage_support.as_events(await store.events(after=0))
    ready = next(
        event["cursor"]
        for event in events
        if event["source"] == "collector"
        and event["projection"].get("state") == "catalogue_ready"
    )
    catalogue = [
        event["cursor"] for event in events if event["source"] == "lody.catalogue"
    ]
    following = next(
        event["cursor"]
        for event in events
        if event["source"] == "collector"
        and event["projection"].get("state") == "following"
    )
    assert catalogue, "Initial reconciliation must journal catalogue metadata."
    assert ready < min(catalogue), "Catalogue replay must follow source readiness."
    assert max(catalogue) < following, (
        "Following health must be committed after all bootstrap catalogue rows."
    )


async def _wait_for_running(store: Store) -> Snapshot:
    """Wait for the observer's live transition within the test deadline.

    Returns
    -------
    Snapshot
        The first public frame with the running session.
    """
    async with asyncio.timeout(2):
        while True:
            snapshot = storage_support.as_snapshot(await store.snapshot())
            if snapshot["sessions"] and snapshot["sessions"][0]["state"] == "running":
                return snapshot
            await asyncio.sleep(0.01)


async def _wait_for_catalogue(store: Store) -> Snapshot:
    """Wait for initial metadata and following health to be committed.

    Returns
    -------
    Snapshot
        The first public frame after initial reconciliation completes.
    """
    async with asyncio.timeout(2):
        while True:
            snapshot = storage_support.as_snapshot(await store.snapshot())
            if snapshot["collector"]["state"] == "following" and any(
                session["repoFullName"] == "leynos/fixture"
                for session in snapshot["sessions"]
            ):
                return snapshot
            await asyncio.sleep(0.01)


def _initial_pr_catalogue() -> Catalogue:
    """Supply stale metadata that requires a delayed GitHub title lookup.

    Returns
    -------
    Catalogue
        One session with an active associated pull request.
    """
    return Catalogue(
        ok=True,
        workspace_id="w1",
        sessions=[
            RawSession(
                id="session",
                title="Stale catalogue title",
                repo_full_name="leynos/fixture",
                pull_requests=[
                    RawPR(url="https://github.com/leynos/fixture/pull/1", status="open")
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_observer_ingests_transition_during_initial_pr_enrichment(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ready observation keeps accepting events before GitHub enrichment finishes."""
    stdout = asyncio.StreamReader()
    stdout.feed_data(storage_support.observer_frame("lody-observer.jsonl"))
    enrichment_started = asyncio.Event()
    release_enrichment = asyncio.Event()
    enrichment_finished = asyncio.Event()

    async def delayed_titles(_urls: list[str]) -> mock.Mock:
        """Hold the catalogue at GitHub enrichment until the event is ingested.

        Returns
        -------
        mock.Mock
            An empty, successful title lookup after release.
        """
        enrichment_started.set()
        await release_enrichment.wait()
        enrichment_finished.set()
        return mock.Mock(records={}, is_partial=False)

    monkeypatch.setattr(
        observation, "child", functools.partial(_controlled_child, stdout=stdout)
    )
    monkeypatch.setattr(observation, "read_pull_requests", delayed_titles)
    async with storage_support.opened_store(tmp_path) as store:
        task = asyncio.create_task(
            observation.Collector(store, "leynos").run(_initial_pr_catalogue())
        )
        try:
            await asyncio.wait_for(enrichment_started.wait(), timeout=2)
            stdout.feed_data(
                storage_support.observer_frame("lody-observer-activity.jsonl")
            )
            snapshot = await _wait_for_running(store)
            assert not enrichment_finished.is_set(), (
                "The observer event must commit while initial enrichment is pending."
            )
            assert snapshot["collector"]["state"] == "catalogue_ready", (
                "Ready enumeration must remain the quiet phase during enrichment."
            )
            source_events = storage_support.as_events(await store.events(after=0))
            assert any(
                event["source"] == "lody.observe"
                and event["projection"].get("state") == "running"
                for event in source_events
            ), "The event must be durably journalled before enrichment finishes."
            release_enrichment.set()
            snapshot = await _wait_for_catalogue(store)
            assert snapshot["sessions"][0]["state"] == "running", (
                "Stale initial catalogue metadata must not erase newer live state."
            )
            await _assert_bootstrap_order(store)
        finally:
            release_enrichment.set()
            await cancel_and_reap((task,))


@pytest.mark.asyncio
async def test_observer_exit_before_ready_does_not_start_catalogue_read(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that closes before ready cannot start catalogue reconciliation."""
    stdout = asyncio.StreamReader()
    stdout.feed_eof()

    catalogue_read = mock.AsyncMock()
    monkeypatch.setattr(
        observation, "child", functools.partial(_controlled_child, stdout=stdout)
    )
    monkeypatch.setattr(observation, "read_catalogue", catalogue_read)
    async with storage_support.opened_store(tmp_path) as store:
        collector = observation.Collector(store, "leynos", github=False)
        collector.generation = await store.begin_generation()
        with pytest.raises(ProtocolError, match="Observer exited"):
            await collector._follow()
        catalogue_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_catalogue_failure_finishes_quiet_phase_without_source_loss(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable catalogue reports a warning while observation continues."""
    stdout = asyncio.StreamReader()
    stdout.feed_data(storage_support.observer_frame("lody-observer.jsonl"))
    monkeypatch.setattr(
        observation, "child", functools.partial(_controlled_child, stdout=stdout)
    )
    catalogue_read = mock.AsyncMock(side_effect=OSError("unavailable"))
    monkeypatch.setattr(observation, "read_catalogue", catalogue_read)
    async with storage_support.opened_store(tmp_path) as store:
        task = asyncio.create_task(observation.Collector(store, "leynos").run())
        try:
            async with asyncio.timeout(2):
                while True:
                    snapshot = storage_support.as_snapshot(await store.snapshot())
                    if snapshot["collector"]["state"] == "following":
                        break
                    await asyncio.sleep(0.01)
            assert "Catalogue refresh unavailable" in str(
                snapshot["collector"]["lastError"]
            ), "A failed initial read must leave the quiet phase with a warning."
            catalogue_read.assert_awaited_once_with("leynos", "lody")
            stdout.feed_data(
                storage_support.observer_frame("lody-observer-activity.jsonl")
            )
            snapshot = await _wait_for_running(store)
            assert snapshot["collector"]["state"] == "following", (
                "Catalogue failure must not disconnect the live observer."
            )
        finally:
            await cancel_and_reap((task,))
