"""Query-scoped fallback reads accepted Lody IDs without path normalization."""

import json
import typing as typ
from urllib.parse import quote

import pytest
from batch_activity_support import seed_unknown_sessions
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


@pytest.mark.asyncio
async def test_query_fallback_preserves_dot_slash_and_percent_identities(
    tmp_path: Path, cmd_mox: CmdMox
) -> None:
    """Real ASGI and CLI boundaries keep exact accepted session identities."""
    session_ids = [".", "..", "a/b", "100%?"]

    def observe(invocation: Invocation) -> Response:
        """Return the exact identity passed by the query-backed endpoint.

        Returns
        -------
        Response
            A persisted observation for one fixture session.
        """
        assert invocation.args[:2] == ["session", "observe"], (
            "The fallback must use only Lody's read-only observation command."
        )
        session_id = invocation.args[2]
        assert session_id in session_ids, "Query decoding must retain an accepted ID."
        return Response(
            stdout=json.dumps({
                "ok": True,
                "version": 1,
                "workspaceId": "w1",
                "session": {
                    "sessionId": session_id,
                    "state": "running",
                    "source": "persisted",
                    "freshness": "synced",
                },
            })
        )

    lody = cmd_mox.spy("lody").runs(observe)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, session_ids)
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            responses = [
                await conductor.simulate_get(
                    "/api/v1/session-activity"
                    f"?sessionId={quote(session_id, safe='')}&includeKnown=true"
                )
                for session_id in session_ids
            ]
            after = (await store.snapshot(), await store.events(0))
    assert [response.status_code for response in responses] == [200] * 4, (
        "Every accepted query identity must resolve through the actual ASGI route."
    )
    assert [
        response.json["session"]["sessionId"] for response in responses
    ] == session_ids, (
        "The fallback must never normalize dot, slash, or percent session IDs."
    )
    assert len(lody.invocations) == 4, "Each uncached raw ID requires one Lody read."
    assert before == after, "The fallback must not change the source journal."


@pytest.mark.parametrize("session_id", ["s" * 257, "nul\0inside"])
@pytest.mark.asyncio
async def test_path_activity_rejects_invalid_raw_id_before_lookup(
    tmp_path: Path, session_id: str
) -> None:
    """Legacy path activity applies the same raw-ID bound as query fallback."""
    async with opened_store(tmp_path) as store:
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get(
                f"/api/v1/sessions/{quote(session_id, safe='')}/activity"
            )
            after = (await store.snapshot(), await store.events(0))
    assert response.status_code == 400, (
        "Invalid path identities must fail before session lookup."
    )
    assert before == after, "Rejected identities must leave journal facts intact."
