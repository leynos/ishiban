"""Exercise batch activity through Falcon and actual isolated CLI processes."""

import json
import typing as typ

import pytest
from batch_activity_support import remember_idle_activity, seed_unknown_sessions
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


def _observe(invocation: Invocation) -> Response:
    """Produce independently successful and unavailable command responses.

    Returns
    -------
    Response
        A complete JSON object written by the real CmdMox shim process.

    Raises
    ------
    AssertionError
        If the API requests an unexpected command or session.
    """
    match invocation.args:
        case ["session", "observe", session_id, "--workspace", "w1", "--json"] if (
            session_id in {"s2", "s3"}
        ):
            return Response(
                stdout=json.dumps({
                    "ok": session_id == "s2",
                    "version": 1,
                    "workspaceId": "w1",
                    "session": {
                        "sessionId": session_id,
                        "state": "running" if session_id == "s2" else "unknown",
                        "source": "persisted" if session_id == "s2" else "metadata",
                        "freshness": "synced",
                    },
                })
            )
        case _:
            message = "Only uncached unknown session observations are allowed."
            raise AssertionError(message)


@pytest.mark.asyncio
async def test_batch_api_reads_mocked_lody_and_keeps_journal_unchanged(
    tmp_path: Path, cmd_mox: CmdMox
) -> None:
    """Cached, successful and unavailable members use separate batch outcomes."""
    lody = cmd_mox.spy("lody").runs(_observe)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1", "s2", "s3"])
        await remember_idle_activity(store, "s1")
        journal_before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({
                    "sessionIds": ["s1", "s2", "s3", "missing"],
                }),
                headers={"content-type": "application/json"},
            )
            journal_after = (await store.snapshot(), await store.events(0))

    by_session = {
        frame["sessionId"]: frame
        for line in response.content.splitlines()
        for frame in [json.loads(line)]
    }
    assert response.status_code == 200, "The ASGI batch route must succeed."
    assert set(by_session) == {"s1", "s2", "s3", "missing"}, (
        "The batch emits one frame for each unique requested identity."
    )
    assert by_session["s1"]["session"]["activitySource"] == "lazy", (
        "The cache hit must be returned without a CLI process."
    )
    assert by_session["s2"]["session"]["state"] == "running", (
        "The fake CLI's valid persisted response must resolve s2."
    )
    assert by_session["s2"]["session"]["activitySource"] == "lazy", (
        "Fresh CLI activity must be labelled in the response."
    )
    assert by_session["s3"]["session"] is None, (
        "The unsuccessful s3 response must not abort other batch members."
    )
    assert by_session["missing"]["session"] is None, (
        "A missing identity must produce a null frame without a CLI call."
    )
    assert len(lody.invocations) == 2, "Exactly two uncached sessions must be read."
    assert {invocation.args[2] for invocation in lody.invocations} == {"s2", "s3"}, (
        "Only uncached unknown sessions should start Lody processes."
    )
    assert journal_after[0] == journal_before[0], (
        "Lazy results must not rewrite the journal."
    )
    assert journal_after[1] == journal_before[1], "Lazy results must not append events."
