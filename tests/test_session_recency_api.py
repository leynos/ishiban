"""Stream lazy history recency per raw session without journal mutations."""

import json
import typing as typ

import pytest
from batch_activity_support import post_with_workspace_identity, seed_unknown_sessions
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import as_snapshot, opened_store

from ishiban.api import create_app
from ishiban.batch_activity_api import MAX_ACTIVITY_FRAME_BYTES
from ishiban.session_recency_api import _frame

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


def _show_recency_member(invocation: Invocation) -> Response:
    """Return verified or foreign metadata for one requested Lody member.

    For example, the ``bad`` member returns a foreign workspace without
    affecting its valid sibling's result.

    Returns
    -------
    Response
        Read-only Lody JSON for the requested test member.
    """
    assert invocation.args[:2] == ["session", "show"], (
        "Family recency must use only session show, not configuration reads."
    )
    session_id = invocation.args[2]
    return Response(
        stdout=json.dumps({
            "ok": True,
            "workspace": {"id": "w1" if session_id != "bad" else "foreign"},
            "session": {"id": session_id},
            "latestHistoryAt": (
                "2026-11-08T16:26:01.199Z" if session_id == "child" else None
            ),
        })
    )


@pytest.mark.asyncio
async def test_recency_batch_isolates_failed_member_and_reuses_show_cache(
    tmp_path: Path, cmd_mox: CmdMox
) -> None:
    """One foreign show result cannot discard a valid sibling or write facts."""
    lody = cmd_mox.spy("lody").runs(_show_recency_member)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["root", "child", "bad"])
        before = (as_snapshot(await store.snapshot()), await store.events(0))
        basis = {
            session["sessionId"]: session.get("lastActivityEventId", 0)
            for session in before[0]["sessions"]
        }
        async with testing.ASGIConductor(create_app(store)) as conductor:
            first = await conductor.simulate_post(
                "/api/v1/sessions/recency",
                body=json.dumps({"sessionIds": ["root", "child", "bad", "missing"]}),
                headers={"content-type": "application/json"},
            )
            second = await conductor.simulate_post(
                "/api/v1/sessions/recency",
                body=json.dumps({"sessionIds": ["child"]}),
                headers={"content-type": "application/json"},
            )
            agent = await conductor.simulate_get("/api/v1/sessions/child/agent")
            after = (await store.snapshot(), await store.events(0))

    frames = [json.loads(line) for line in first.content.splitlines()]
    by_id = {frame["sessionId"]: frame for frame in frames}
    assert first.status_code == 200, "The bounded recency route must be mounted."
    assert second.status_code == 200, "A cached recency read must also succeed."
    assert agent.status_code == 200, (
        "The inspector metadata route must share the verified show reader."
    )
    assert len(frames) == 4, "Every requested raw ID needs one result."
    assert all(frame["workspaceId"] == "w1" for frame in frames), (
        "Every result must carry the configured workspace identity."
    )
    assert by_id["root"]["outcome"] == "available", (
        "A verified empty history is an available fact, not a failed read."
    )
    assert by_id["root"]["latestHistoryAt"] is None, (
        "An empty history must remain distinct from catalogue creation time."
    )
    assert by_id["child"]["latestHistoryAt"] == "2026-11-08T16:26:01.199Z", (
        "The outer show history time must identify the newer tab."
    )
    assert by_id["bad"]["outcome"] == "unavailable", (
        "A foreign show result must fail only its own member."
    )
    assert by_id["missing"]["outcome"] == "unavailable", (
        "A missing raw session must skip Lody without failing the batch."
    )
    assert all(
        by_id[session_id]["lastActivityEventId"] == basis[session_id]
        for session_id in ("root", "child", "bad")
    ), "Each frame must echo the execution watermark used for its show read."
    assert len(lody.invocations) == 3, (
        "Recency and inspector metadata must share the verified show read."
    )
    assert before == after, (
        "Recency reads must leave journal and projections untouched."
    )


@pytest.mark.asyncio
async def test_recency_rejects_identity_before_stream_when_basis_can_overflow_frame(
    tmp_path: Path,
) -> None:
    """A possible 19-digit execution watermark is included in preflight."""
    base = len(_frame(("", "s1"), 0, "available", "x" * 64))
    workspace = "w" * (MAX_ACTIVITY_FRAME_BYTES - base - 1)
    assert (
        len(_frame((workspace, "s1"), 0, "available", "x" * 64))
        < MAX_ACTIVITY_FRAME_BYTES
    ), "A zero-basis preflight would incorrectly accept this identity."
    response = await post_with_workspace_identity(
        tmp_path, workspace, "/api/v1/sessions/recency"
    )
    assert response.status_code == 413, (
        "The server must reject an unrepresentable identity before opening NDJSON."
    )
    assert len(response.content) < 8_192, "The preflight error must remain bounded."
