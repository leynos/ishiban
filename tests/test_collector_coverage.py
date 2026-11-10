"""Collector recovery preserves health history without fabricating session outcomes."""

import asyncio
import typing as typ
from unittest import mock

import pytest
from storage_support import as_events, as_snapshot, opened_store

from ishiban import collector as observation
from ishiban.protocol import Catalogue, ProtocolError

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_error", "expected_summary"),
    [
        (ProtocolError("Wrong workspace"), "Wrong workspace"),
        (
            OSError("private transport details"),
            "Lody source failure (OSError); reconnecting.",
        ),
    ],
    ids=["protocol-diagnostic", "sanitized-transport-error"],
)
async def test_collector_retries_preserve_errors_and_release_on_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_error: Exception,
    expected_summary: str,
) -> None:
    """Retries journal their source failures and cancellation records stopped health."""
    original_sleep = asyncio.sleep
    delays: list[float] = []

    async def two_attempts(delay: float) -> None:
        """Advance one backoff and cancel the next without delaying the test.

        Raises
        ------
        asyncio.CancelledError
            After two source attempts have reached their backoff boundary.
        """
        if delay < 1:
            await original_sleep(delay)
            return
        delays.append(delay)
        if len(delays) > 1:
            raise asyncio.CancelledError
        await original_sleep(0)

    source = mock.AsyncMock(side_effect=source_error)
    monkeypatch.setattr(observation, "read_catalogue", source)
    monkeypatch.setattr(observation.asyncio, "sleep", two_attempts)
    async with opened_store(tmp_path) as store:
        with pytest.raises(asyncio.CancelledError):
            await observation.Collector(store, "leynos", github=False).run()
        snapshot = as_snapshot(await store.snapshot())
        failures = [
            event["projection"]
            for event in as_events(await store.events(0))
            if event["projection"].get("state") == "disconnected"
        ]
        assert source.await_count == 2, (
            "The collector must reconnect after source loss."
        )
        assert delays[0] < delays[1], (
            "Reconnect backoff must increase between attempts."
        )
        assert [failure.get("lastError") for failure in failures] == [
            expected_summary
        ] * 2, (
            "Health history must preserve safe diagnostics for every failed generation."
        )
        assert snapshot["collector"]["state"] == "stopped", (
            "Cancelling reconnect must close collector ownership explicitly."
        )
        assert snapshot["sessions"] == [], "Source failure cannot manufacture sessions."


@pytest.mark.asyncio
@pytest.mark.parametrize("source_error", [None, OSError("temporarily unavailable")])
async def test_periodic_refresh_preserves_collector_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_error: OSError | None
) -> None:
    """A refresh reports stale associations without stopping observation."""
    original_sleep = asyncio.sleep
    waits: list[float] = []

    async def one_refresh(delay: float) -> None:
        """Run exactly one catalogue tick while preserving unrelated async yields.

        Raises
        ------
        asyncio.CancelledError
            After the first refresh has completed.
        """
        if delay != 300:
            await original_sleep(delay)
            return
        waits.append(delay)
        if len(waits) > 1:
            raise asyncio.CancelledError
        await original_sleep(0)

    source = mock.AsyncMock(
        return_value=Catalogue(ok=True, workspace_id="w1", sessions=[]),
        side_effect=source_error,
    )
    monkeypatch.setattr(observation, "read_catalogue", source)
    monkeypatch.setattr(observation.asyncio, "sleep", one_refresh)
    async with opened_store(tmp_path) as store:
        collector = observation.Collector(store, "leynos", github=False)
        collector.generation = await store.begin_generation()
        with pytest.raises(asyncio.CancelledError):
            await collector._refresh()
        health = as_snapshot(await store.snapshot())["collector"]
        source.assert_awaited_once_with("leynos", "lody")
        assert health["state"] == "following", (
            "Refresh failure cannot imply observer loss."
        )
        assert (health.get("lastError") is not None) == (source_error is not None), (
            "Failed refreshes alone mark associations as potentially stale."
        )
