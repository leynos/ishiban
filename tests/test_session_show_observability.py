"""Fixed safe diagnostics for rejected Lody session-show envelopes."""

import json
import logging
import typing as typ

import pytest
from cmd_mox import Invocation, Response

from ishiban.session_show import SessionShowReader

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox


@pytest.mark.parametrize(
    ("case", "category"),
    [("negative", "negative"), ("workspace", "protocol"), ("session", "protocol")],
)
@pytest.mark.asyncio
async def test_rejected_show_logs_one_safe_category_and_caches_unavailability(
    cmd_mox: CmdMox, caplog: pytest.LogCaptureFixture, case: str, category: str
) -> None:
    """One rejected load logs safely; a cache hit stays quiet, then retries."""
    invalid = {
        "ok": case != "negative",
        "workspace": {"id": "private-workspace" if case == "workspace" else "w1"},
        "session": {
            "id": "private-session" if case == "session" else "child",
            "agentType": "private-agent",
        },
        "latestHistoryAt": None,
        "error": "private-error",
    }
    valid = {
        "ok": True,
        "workspace": {"id": "w1"},
        "session": {"id": "child"},
        "latestHistoryAt": None,
    }
    responses = [
        Response(stdout=json.dumps(invalid)),
        Response(stdout=json.dumps(valid)),
    ]

    def show(_invocation: Invocation) -> Response:
        """Return the rejected envelope once, then a verified retry.

        Returns
        -------
        Response
            The next bounded command fixture response.
        """
        return responses.pop(0)

    lody = cmd_mox.spy("lody").runs(show)
    reader = SessionShowReader("w1", "w1")
    try:
        with caplog.at_level(logging.WARNING, logger="ishiban"):
            assert await reader.read("child", 40) is None, (
                "A rejected show must remain unavailable."
            )
            assert await reader.read("child", 40) is None, (
                "A cached rejection must remain unavailable without another log."
            )
            assert await reader.read("child", 41) is not None, (
                "A newer basis must retry and accept a valid show quietly."
            )
    finally:
        await reader.close()
    records = [
        record for record in caplog.records if record.name.startswith("ishiban.")
    ]
    messages = [record.getMessage() for record in records]
    assert messages == [f"Lody metadata unavailable category={category}"], (
        "Each owned rejection must emit one fixed category, without a cache-hit log."
    )
    assert not any(record.exc_info for record in records), (
        "Rejection logs must not expose an exception traceback."
    )
    assert all(
        secret not in message
        for message in messages
        for secret in ("private-", "child")
    ), "Logs must never expose response fields or requested identities."
    assert len(lody.invocations) == 2, "The cache hit must not start another CLI read."
