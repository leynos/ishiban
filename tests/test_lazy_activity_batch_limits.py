"""Cover queue and request bounds for concurrent lazy activity reads."""

import asyncio
import typing as typ

import msgspec
import pytest

from ishiban import lazy_activity
from tests.lody_process_support import create_fake_lody, wait_for_calls

if typ.TYPE_CHECKING:
    import pathlib


def _slow_service(
    tmp_path: pathlib.Path, delay: float, *, timeout: float = 20.0
) -> tuple[lazy_activity.LazyActivity, pathlib.Path]:
    """Create a valid fake observer whose response arrives after a short delay.

    Returns
    -------
    tuple of LazyActivity and pathlib.Path
        The observer service and its invocation log.
    """
    response = {
        "ok": True,
        "version": 1,
        "workspaceId": "workspace-1",
        "session": {
            "sessionId": "@SESSION_ID@",
            "state": "running",
            "source": "persisted",
            "freshness": "synced",
            "latestTurn": {"userTurnId": "turn-1", "state": "failed"},
        },
    }
    payload = msgspec.json.encode(response).decode("utf-8")
    response_code = (
        f"time.sleep({delay!r})\npayload = {payload!r}.replace('@SESSION_ID@', args[2])"
    )
    executable, call_log = create_fake_lody(tmp_path, response_code)
    service = lazy_activity.LazyActivity(
        "workspace-1", "leynos", str(executable), timeout=timeout
    )
    return service, call_log


@pytest.mark.asyncio
async def test_unique_inflight_limit_reuses_keys_and_rejects_overflow(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing keys join while excess unique observations fail closed."""
    monkeypatch.setattr(lazy_activity, "MAX_IN_FLIGHT_OBSERVATIONS", 2)
    service, call_log = _slow_service(tmp_path, 0.3)
    pending = [
        asyncio.create_task(service.read(f"session-{index}", 1)) for index in range(2)
    ]
    await wait_for_calls(call_log, 2)
    duplicate = asyncio.create_task(service.read("session-0", 1))
    assert await service.read("overflow-session", 1) is None, (
        "A new key must fail closed when all in-flight slots are occupied."
    )
    assert await duplicate is not None, "An existing key must still join its observer."
    results = await asyncio.gather(*pending)
    assert all(result is not None for result in results), (
        "Existing observers must complete after overflow is rejected."
    )
    assert len(await wait_for_calls(call_log, 2)) == 2, (
        "Rejecting an overflow key must not start another subprocess."
    )
    await service.close()


@pytest.mark.asyncio
async def test_queued_observation_gets_full_child_timeout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semaphore wait time does not consume the queued child's process budget."""
    monkeypatch.setattr(lazy_activity, "MAX_CONCURRENT_OBSERVERS", 1)
    service, _call_log = _slow_service(tmp_path, 0.25, timeout=0.4)
    results = await asyncio.gather(
        service.read("session-first", 1),
        service.read("session-queued", 1),
    )
    assert all(result is not None for result in results), (
        "Each child must receive its own timeout after leaving the queue."
    )
    await service.close()


@pytest.mark.asyncio
async def test_total_observation_lifetime_includes_semaphore_wait(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued observer expires at the service-wide lifetime boundary."""
    monkeypatch.setattr(lazy_activity, "MAX_CONCURRENT_OBSERVERS", 1)
    service, call_log = _slow_service(tmp_path, 0.2)
    first = asyncio.create_task(service.read("session-first", 1))
    await wait_for_calls(call_log)
    monkeypatch.setattr(lazy_activity, "MAX_OBSERVATION_LIFETIME_SECONDS", 0.05)
    assert await service.read("session-queued", 1) is None, (
        "A queued observer must fail closed when its total lifetime expires."
    )
    assert await first is not None, "The process holding the semaphore must complete."
    assert len(await wait_for_calls(call_log)) == 1, (
        "A queued observer that expires must not start a subprocess."
    )
    await service.close()
