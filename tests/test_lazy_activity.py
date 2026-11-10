"""Exercise on-demand Lody observation through real fake CLI processes."""

import asyncio
import textwrap
import typing as typ

import msgspec
import pytest

from ishiban import lazy_activity
from ishiban.domain import ObservedSession
from tests.lody_process_support import create_fake_lody, wait_for_calls

if typ.TYPE_CHECKING:
    import pathlib

    from tests.lody_reader_fixtures import (
        LazyActivityFakeOptions,
        LazyActivityResponseOptions,
    )


def _response(**options: typ.Unpack[LazyActivityResponseOptions]) -> dict[str, object]:
    """Build one singular response with realistic persisted turn evidence.

    Returns
    -------
    dict of str to object
        A root response containing one persisted session and failed latest turn.
    """
    session_id = options.get("session_id", "@SESSION_ID@")
    workspace_id = options.get("workspace_id", "workspace-1")
    ok = options.get("ok", True)
    version = options.get("version", 1)
    state = options.get("state", "running")
    source = options.get("source", "persisted")
    freshness = options.get("freshness", "synced")
    turn_state = options.get("turn_state", "failed")
    return {
        "ok": ok,
        "version": version,
        "workspaceId": workspace_id,
        "session": {
            "sessionId": session_id,
            "state": state,
            "source": source,
            "freshness": freshness,
            "latestTurn": {
                "userTurnId": "turn-1",
                "state": turn_state,
                "error": "command failed",
            },
        },
    }


def _fake_lody(
    tmp_path: pathlib.Path,
    response: dict[str, object] | str,
    **options: typ.Unpack[LazyActivityFakeOptions],
) -> tuple[pathlib.Path, pathlib.Path]:
    """Create an executable fake CLI and a path recording each invocation.

    Returns
    -------
    tuple of pathlib.Path
        The executable path followed by the invocation log path.
    """
    linger_after_output = options.get("linger_after_output", 0)
    delay_before_output = options.get("delay_before_output", 0)
    track_concurrency = options.get("track_concurrency", False)
    payload = (
        response
        if isinstance(response, str)
        else msgspec.json.encode(response).decode("utf-8")
    )
    concurrency_code = ""
    if track_concurrency:
        concurrency_code = textwrap.dedent(
            f"""
            import fcntl
            lock_path = pathlib.Path({str(tmp_path / "counter.lock")!r})
            active_path = pathlib.Path({str(tmp_path / "active")!r})
            maximum_path = pathlib.Path({str(tmp_path / "maximum")!r})
            with lock_path.open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                active = int(
                    active_path.read_text() if active_path.exists() else "0"
                ) + 1
                active_path.write_text(str(active))
                previous = int(
                    maximum_path.read_text() if maximum_path.exists() else "0"
                )
                maximum_path.write_text(str(max(active, previous)))
                fcntl.flock(lock, fcntl.LOCK_UN)
            time.sleep({delay_before_output!r})
            with lock_path.open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                active_path.write_text(str(int(active_path.read_text()) - 1))
                fcntl.flock(lock, fcntl.LOCK_UN)
            """
        )
    elif delay_before_output:
        concurrency_code = f"time.sleep({delay_before_output!r})\n"
    response_code = (
        f"payload = {payload!r}.replace('@SESSION_ID@', args[2])\n{concurrency_code}"
    )
    return create_fake_lody(
        tmp_path,
        response_code,
        linger_after_output=linger_after_output,
    )


@pytest.mark.asyncio
async def test_read_returns_persisted_session_before_cli_eof(
    tmp_path: pathlib.Path,
) -> None:
    """A complete response is usable even when the CLI transport lingers."""
    executable, call_log = _fake_lody(
        tmp_path,
        _response(),
        linger_after_output=120,
    )
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    observation = await asyncio.wait_for(service.read("session-1", 9), timeout=3)
    assert isinstance(observation, ObservedSession), (
        "A valid singular persisted response must produce an observed session."
    )
    assert observation.state == "running", (
        "The reader must preserve the persisted session activity state."
    )
    assert observation.latest_turn is not None, (
        "The reader must preserve the persisted latest turn."
    )
    assert observation.latest_turn.error == "command failed", (
        "Turn errors must survive lazy observation for the inspector."
    )
    assert await wait_for_calls(call_log) == [
        "session\tobserve\tsession-1\t--workspace\tleynos\t--json"
    ], (
        "The CLI must receive the session, selector, and JSON flags as separate "
        "arguments."
    )
    await service.close()


@pytest.mark.parametrize(
    ("response", "case"),
    [
        (_response(workspace_id="other-workspace"), "wrong workspace"),
        (_response(session_id="other-session"), "wrong session"),
        (_response(ok=False), "unsuccessful response"),
        (_response(version=2), "unsupported version"),
        (_response(source="metadata"), "metadata-only source"),
        (_response(state="unknown"), "unknown activity"),
        (_response(state="sending"), "unknown activity vocabulary"),
        (_response(turn_state="lost"), "unknown turn vocabulary"),
        (_response(freshness="stale"), "unknown freshness vocabulary"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.asyncio
async def test_invalid_or_unpersisted_response_returns_none(
    tmp_path: pathlib.Path,
    response: dict[str, object],
    case: str,
) -> None:
    """Untrusted identity or evidence never becomes activity."""
    executable, _call_log = _fake_lody(tmp_path, response)
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    assert await service.read("session-1", 1) is None, (
        f"A response with {case} must fail closed."
    )
    await service.close()


@pytest.mark.asyncio
async def test_invalid_cli_result_is_cached_briefly(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed response is not retried until its negative cache expires."""
    clock = [50.0]
    monkeypatch.setattr(lazy_activity, "_monotonic_time", lambda: clock[0])
    executable, call_log = _fake_lody(tmp_path, "not-json")
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    assert await service.read("session-1", 1) is None, (
        "Malformed observer output must not become session activity."
    )
    assert await service.read("session-1", 1) is None, (
        "A cached unavailable result must remain unavailable."
    )
    assert len(await wait_for_calls(call_log)) == 1, (
        "A negative cache hit must avoid another CLI process."
    )
    clock[0] += lazy_activity.FAILURE_CACHE_SECONDS + 1
    assert await service.read("session-1", 1) is None, (
        "The malformed response must remain unavailable after retry."
    )
    assert len(await wait_for_calls(call_log, 2)) == 2, (
        "An expired negative cache entry must allow one retry."
    )
    await service.close()


@pytest.mark.asyncio
async def test_success_cache_is_revision_scoped_and_expires(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted results are reused only for their key and five-minute window."""
    clock = [100.0]
    monkeypatch.setattr(lazy_activity, "_monotonic_time", lambda: clock[0])
    executable, call_log = _fake_lody(tmp_path, _response())
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    first = await service.read("session-1", 1)
    assert first is not None, "A valid persisted observation must be returned."
    assert await service.read("session-1", 1) is first, (
        "The same unexpired revision must use its cached result."
    )
    assert await service.read("session-1", 2) is not None, (
        "A new revision must fetch fresh activity."
    )
    clock[0] += lazy_activity.SUCCESS_CACHE_SECONDS + 1
    assert await service.read("session-1", 1) is not None, (
        "An expired successful entry must be refreshed."
    )
    assert len(await wait_for_calls(call_log, 3)) == 3, (
        "Revision changes and expiry must each cause one new observer process."
    )
    await service.close()


@pytest.mark.asyncio
async def test_same_key_reads_share_one_process_when_a_waiter_is_cancelled(
    tmp_path: pathlib.Path,
) -> None:
    """Cancelling one waiter leaves the shared observation alive for others."""
    executable, call_log = _fake_lody(
        tmp_path,
        _response(),
        delay_before_output=0.2,
    )
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    cancelled_waiter = asyncio.create_task(service.read("session-1", 4))
    await wait_for_calls(call_log)
    remaining_waiter = asyncio.create_task(service.read("session-1", 4))
    await asyncio.sleep(0.02)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    result = await remaining_waiter
    assert result is not None, "The surviving waiter must receive the shared result."
    assert len(await wait_for_calls(call_log)) == 1, (
        "Waiters for the same revision must share one CLI process."
    )
    await service.close()


@pytest.mark.asyncio
async def test_unrelated_reads_use_at_most_four_cli_processes(
    tmp_path: pathlib.Path,
) -> None:
    """The observer semaphore caps parallel child processes at four."""
    executable, _call_log = _fake_lody(
        tmp_path,
        _response(),
        delay_before_output=0.12,
        track_concurrency=True,
    )
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    results = await asyncio.gather(
        *(service.read(f"session-{index}", 1) for index in range(8))
    )
    assert all(result is not None for result in results), (
        "Each valid independent observation must complete."
    )
    maximum = await asyncio.to_thread(
        (tmp_path / "maximum").read_text,
        encoding="utf-8",
    )
    assert maximum == "4", "No more than four Lody observer processes may overlap."
    await service.close()


@pytest.mark.asyncio
async def test_cache_evicts_least_recently_used_entry(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An LRU cache keeps recent entries while enforcing its configured bound."""
    monkeypatch.setattr(lazy_activity, "MAX_CACHE_ENTRIES", 2)
    executable, call_log = _fake_lody(tmp_path, _response())
    service = lazy_activity.LazyActivity("workspace-1", "leynos", str(executable))
    assert await service.read("session-a", 1) is not None, "The first entry must load."
    assert await service.read("session-b", 1) is not None, "The second entry must load."
    assert await service.read("session-a", 1) is not None, "A hit must refresh recency."
    assert await service.read("session-c", 1) is not None, "The third entry must load."
    assert await service.read("session-b", 1) is not None, "An evicted entry reloads."
    assert len(await wait_for_calls(call_log, 4)) == 4, (
        "The least recently used key must be evicted when the cache is full."
    )
    await service.close()


@pytest.mark.asyncio
async def test_timeout_and_close_cancel_service_owned_children(
    tmp_path: pathlib.Path,
) -> None:
    """Timeouts fail closed and close cancels a still-running child task."""
    timeout_executable, _timeout_log = _fake_lody(
        tmp_path / "timeout",
        _response(),
        delay_before_output=10,
    )
    timeout_service = lazy_activity.LazyActivity(
        "workspace-1",
        "leynos",
        str(timeout_executable),
        timeout=0.2,
    )
    assert await timeout_service.read("session-1", 1) is None, (
        "An observation exceeding its timeout must fail closed."
    )
    await timeout_service.close()

    close_directory = tmp_path / "close"
    close_directory.mkdir()
    close_executable, call_log = _fake_lody(
        close_directory,
        _response(),
        delay_before_output=10,
    )
    close_service = lazy_activity.LazyActivity(
        "workspace-1", "leynos", str(close_executable)
    )
    pending_read = asyncio.create_task(close_service.read("session-2", 1))
    await wait_for_calls(call_log)
    await close_service.close()
    completion = await asyncio.gather(pending_read, return_exceptions=True)
    assert isinstance(completion[0], asyncio.CancelledError), (
        "Service shutdown must cancel its shared pending observation."
    )
    assert await close_service.read("session-2", 1) is None, (
        "A closed service must not create new CLI processes."
    )
