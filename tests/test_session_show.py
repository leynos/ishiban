"""Read bounded session-show metadata without losing identity or recency facts."""

import asyncio
import json
import typing as typ

import pytest
from cmd_mox import Invocation, Response

from ishiban import session_show
from ishiban.session_show import SessionShowMetadata, SessionShowReader

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from cmd_mox import CmdMox, SpyCommand


def _show_response(
    *,
    workspace_id: str = "w1",
    session_id: str = "child",
    history_time: str | None = "2026-11-08T16:26:01.199Z",
    session_fields: dict[str, object] | None = None,
) -> Response:
    """Build one CLI envelope while each test chooses the facts it varies.

    For example, a foreign workspace exercises identity rejection without
    changing the command response shape used by the cache tests.

    Returns
    -------
    Response
        One JSON encoded session-show result for CmdMox.
    """
    return Response(
        stdout=json.dumps({
            "ok": True,
            "workspace": {"id": workspace_id},
            "session": {"id": session_id, **(session_fields or {})},
            "latestHistoryAt": history_time,
        })
    )


def _reader_for_show(
    cmd_mox: CmdMox, show: cabc.Callable[[Invocation], Response]
) -> tuple[SessionShowReader, SpyCommand]:
    """Wire one CmdMox show callback to a workspace-bound reader.

    For example, cache tests can vary responses while counting actual CLI
    invocations through the returned spy.

    Returns
    -------
    tuple[SessionShowReader, SpyCommand]
        The reader and its command spy.
    """
    return SessionShowReader("w1", "w1"), cmd_mox.spy("lody").runs(show)


@pytest.mark.parametrize("has_history_field", [False, True], ids=["missing", "empty"])
@pytest.mark.asyncio
async def test_show_requires_explicit_history_fact(
    cmd_mox: CmdMox, *, has_history_field: bool
) -> None:
    """Omitted history is unavailable; explicit null confirms empty history."""
    payload: dict[str, object] = {
        "ok": True,
        "workspace": {"id": "w1"},
        "session": {"id": "child"},
    }
    if has_history_field:
        payload["latestHistoryAt"] = None
    cmd_mox.spy("lody").returns(stdout=json.dumps(payload))
    result = await SessionShowReader("w1", "w1").read("child", 40)
    assert (result is not None) is has_history_field, (
        "Only an explicit empty-history fact may produce available metadata."
    )


@pytest.mark.parametrize("session_id", ["child", "-example"])
@pytest.mark.asyncio
async def test_show_keeps_opaque_id_after_option_separator(
    cmd_mox: CmdMox, session_id: str
) -> None:
    """CLI option parsing must not interpret a supported session ID as a flag."""
    spy = cmd_mox.spy("lody").runs(
        lambda _invocation: _show_response(session_id=session_id)
    )
    result = await SessionShowReader("w1", "w1").read(session_id, 40)
    assert result is not None, "The exact requested identity must remain available."
    assert spy.invocations[0].args == [
        "session",
        "show",
        "--workspace",
        "w1",
        "--json",
        "--",
        session_id,
    ], "All options must precede the opaque session ID and option separator."


async def _read_twice(
    reader: SessionShowReader, basis: int
) -> tuple[SessionShowMetadata | None, SessionShowMetadata | None]:
    """Read one unchanged execution basis twice to probe cache reuse.

    For example, a cached failure remains ``None`` until its short TTL ends.

    Returns
    -------
    tuple[SessionShowMetadata or None, SessionShowMetadata or None]
        The initial result and its immediate cache result.
    """
    first = await reader.read("child", basis)
    return first, await reader.read("child", basis)


@pytest.mark.asyncio
async def test_show_reader_reuses_one_validated_result_per_execution_basis(
    cmd_mox: CmdMox,
) -> None:
    """Agent labels and recency can share a show read until execution changes."""

    def show(invocation: Invocation) -> Response:
        """Return the requested session's public show envelope.

        Returns
        -------
        Response
            One identity-scoped response with outer history recency.
        """
        assert invocation.args == [
            "session",
            "show",
            "--workspace",
            "w1",
            "--json",
            "--",
            "child",
        ], "Only the selected child may be read through session show."
        return _show_response(
            session_fields={
                "agentType": "claude-code",
                "agentConfigId": "config-1",
                "createdAt": "2026-11-05T14:55:35.407Z",
                "conversation": "private field must not be retained",
            }
        )

    reader, lody = _reader_for_show(cmd_mox, show)
    first, second = await _read_twice(reader, 40)
    changed = await reader.read("child", 41)
    assert first is not None, "A verified show result must be available."
    assert second is first, "An unchanged basis must reuse one result."
    assert first.latest_history_at == "2026-11-08T16:26:01.199Z", (
        "Outer latestHistoryAt must be retained independently of catalogue times."
    )
    assert first.agent_type == "claude-code", (
        "The shared show result must retain only requested agent labels."
    )
    assert changed is not None, "A newer basis must still return metadata."
    assert len(lody.invocations) == 2, (
        "A new execution watermark must invalidate the recency cache."
    )


@pytest.mark.parametrize(
    ("workspace_id", "session_id"),
    [("other", "child"), ("w1", "other")],
)
@pytest.mark.asyncio
async def test_show_reader_rejects_foreign_identity(
    cmd_mox: CmdMox, workspace_id: str, session_id: str
) -> None:
    """A foreign show result cannot select a tab or supply inspector labels."""
    cmd_mox.spy("lody").runs(
        lambda _invocation: _show_response(
            workspace_id=workspace_id, session_id=session_id
        )
    )
    assert await SessionShowReader("w1", "w1").read("child", 40) is None, (
        "Foreign metadata must remain unavailable."
    )


@pytest.mark.parametrize(
    "history_time",
    ["yesterday", "2026-11-08T16:26:01", "2026-11-08 16:26:01Z", "x" * 65],
)
@pytest.mark.asyncio
async def test_show_reader_rejects_supplied_invalid_history_time(
    cmd_mox: CmdMox, history_time: str
) -> None:
    """Invalid supplied recency is a failed read, not an empty history."""
    cmd_mox.spy("lody").runs(
        lambda _invocation: _show_response(history_time=history_time)
    )
    assert await SessionShowReader("w1", "w1").read("child", 40) is None, (
        "Untrusted timestamps must not turn into a successful empty-history fact."
    )


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_show_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One browser cancellation cannot abandon another waiter for the same tab."""
    reader = SessionShowReader("w1", "w1")
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def blocked(session_id: str) -> SessionShowMetadata:
        """Hold one shared request until both waiters have joined.

        Returns
        -------
        SessionShowMetadata
            One verified test identity after release.
        """
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return SessionShowMetadata(session_id, None, None, None)

    monkeypatch.setattr(reader, "_read_session", blocked)
    first = asyncio.create_task(reader.read("child", 40))
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(reader.read("child", 40))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    result = await asyncio.wait_for(second, 1)
    assert result is not None, "The surviving waiter must receive a result."
    assert result.session_id == "child", "The shared read must keep its identity."
    assert calls == 1, "One execution basis must own just one show read."
    await reader.close()


@pytest.mark.asyncio
async def test_show_reader_limits_children_and_queue_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued third member times out within the total lifetime bound."""
    reader = SessionShowReader("w1", "w1")
    two_started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    peak = 0

    async def blocked(session_id: str) -> SessionShowMetadata:
        """Record active children while withholding their test responses.

        Returns
        -------
        SessionShowMetadata
            The requested identity when released.
        """
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            two_started.set()
        try:
            await release.wait()
            return SessionShowMetadata(session_id, None, None, None)
        finally:
            active -= 1

    monkeypatch.setattr(reader, "_read_session", blocked)
    first = asyncio.create_task(reader.read("first", 0))
    second = asyncio.create_task(reader.read("second", 0))
    await asyncio.wait_for(two_started.wait(), 1)
    monkeypatch.setattr(session_show, "MAX_SHOW_LIFETIME_SECONDS", 0.02)
    queued = await asyncio.wait_for(reader.read("third", 0), 1)
    assert queued is None, "The queued member must time out before starting a child."
    assert peak == 2, "No more than two session-show reads may run together."
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    await reader.close()


@pytest.mark.asyncio
async def test_closing_show_reader_reaps_owned_inflight_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API shutdown cancels and awaits a child stalled after request exit."""
    reader = SessionShowReader("w1", "w1")
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked(_session_id: str) -> SessionShowMetadata:
        """Signal when the service cancels its owned task.

        Returns
        -------
        SessionShowMetadata
            Unreachable because shutdown cancels the wait.

        Raises
        ------
        asyncio.CancelledError
            When the service reaps the in-flight read.
        """
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return SessionShowMetadata("unused", None, None, None)

    monkeypatch.setattr(reader, "_read_session", blocked)
    waiter = asyncio.create_task(reader.read("child", 40))
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(reader.close(), 1)
    assert cancelled.is_set(), "The owned child must be cancelled and reaped."
    assert isinstance(
        (await asyncio.gather(waiter, return_exceptions=True))[0],
        asyncio.CancelledError,
    ), "A caller waiting through shutdown must observe cancellation."


@pytest.mark.asyncio
async def test_show_reader_uses_short_failure_and_long_success_ttls(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed show retries soon while verified history remains reusable."""
    clock = [100.0]
    monkeypatch.setattr(session_show, "_monotonic_time", lambda: clock[0])
    calls = 0

    def show(_invocation: Invocation) -> Response:
        """Fail once, then return verified recency to exercise both TTLs.

        Returns
        -------
        Response
            A foreign or workspace-scoped session-show envelope.
        """
        nonlocal calls
        calls += 1
        return _show_response(workspace_id="foreign" if calls == 1 else "w1")

    reader, _lody = _reader_for_show(cmd_mox, show)
    failed, cached_failure = await _read_twice(reader, 40)
    assert failed is None, "A foreign result must enter only the short failure cache."
    assert cached_failure is None, (
        "The short failure cache must avoid an immediate retry."
    )
    assert calls == 1, "A cached failure must not launch another CLI process."
    clock[0] += session_show.FAILURE_CACHE_SECONDS + 1
    recovered, cached_success = await _read_twice(reader, 40)
    assert recovered is not None, "The expired failure must retry and recover."
    assert cached_success is recovered, (
        "A verified result must use the longer success cache."
    )
    assert calls == 2, "A success cache hit must avoid another CLI process."
    clock[0] += session_show.SUCCESS_CACHE_SECONDS + 1
    assert await reader.read("child", 40) is not None, (
        "An expired success entry must refresh its history metadata."
    )
    assert calls == 3, "A TTL-expired success must start one new read."
