"""Exercise browser inspector URLs against Falcon's exact-ID routes."""

import json
import typing as typ
from unittest import mock
from urllib.parse import quote

import pytest
from bun_test_capture import capture_bun_test_output
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app
from ishiban.domain import CatalogueEntry, PullRequest
from ishiban.pull_request_details import PullRequestTitles
from ishiban.session_agent import AgentDetails, SessionAgentDetails

PR_URL = "https://github.com/example/project/pull/123"

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.asyncio
async def test_browser_inspector_urls_preserve_exact_source_ids(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dot, slash and percent IDs reach agent and PR readers without writes."""
    captured = json.loads(
        await capture_bun_test_output(
            tmp_path,
            test_file="tests/inspector-request-contract.test.tsx",
            variable="ISHIBAN_INSPECTOR_REQUEST_CAPTURE",
        )
    )
    ids = [item["sessionId"] for item in captured]
    agent_reader = mock.AsyncMock(return_value=AgentDetails("codex", None, None))
    title_reader = mock.AsyncMock(return_value={PR_URL: "Resolved title"})
    monkeypatch.setattr(SessionAgentDetails, "read", agent_reader)
    monkeypatch.setattr(PullRequestTitles, "read", title_reader)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        for session_id in ids:
            await store.catalogue(
                CatalogueEntry(
                    session_id=session_id,
                    machine_id="machine",
                    title="Inspector source",
                    archived=False,
                    repo_full_name="example/project",
                    branch_name="main",
                    pull_requests=[PullRequest(PR_URL, "merged")],
                    stage="merged",
                    stage_reason="The PR was merged.",
                ),
                generation,
            )
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            for item in captured:
                agent = await conductor.simulate_get(item["agent"])
                titles = await conductor.simulate_get(item["titles"])
                assert agent.status_code == titles.status_code == 200, (
                    "Browser URL normalization must not lose the selected source ID."
                )
                assert (
                    agent.json["sessionId"]
                    == titles.json["sessionId"]
                    == item["sessionId"]
                ), "Both inspector readers must use the exact source identity."
            after = (await store.snapshot(), await store.events(0))
    assert before == after, "Inspector enrichment must leave the journal unchanged."
    assert agent_reader.await_count == title_reader.await_count == len(ids), (
        "Every accepted ID must reach each scoped reader once."
    )
    assert [call.args[0] for call in agent_reader.await_args_list] == ids, (
        "The agent reader must receive each exact requested identity."
    )
    assert title_reader.await_args_list == [mock.call([PR_URL]) for _ in ids], (
        "The title reader must receive the selected projections' PR URLs."
    )


@pytest.mark.parametrize("session_id", [".", "..", "a/b", "100%?"])
@pytest.mark.asyncio
async def test_query_paged_detail_preserves_opaque_session_id(
    tmp_path: pathlib.Path, session_id: str
) -> None:
    """The session-detail alias reads any accepted raw ID without normalization."""
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.catalogue(
            CatalogueEntry(
                session_id=session_id,
                machine_id="machine",
                title="Paged detail",
                archived=False,
                repo_full_name="example/project",
                branch_name="main",
                pull_requests=[],
                stage="planning",
                stage_reason="No PR evidence.",
            ),
            generation,
        )
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get(
                f"/api/v1/session-detail?sessionId={quote(session_id, safe='')}"
            )
            after = (await store.snapshot(), await store.events(0))
    assert response.status_code == 200, "The query route must reach the paged reader."
    assert response.json["session"]["sessionId"] == session_id, (
        "The detail response must retain the raw identity."
    )
    assert before == after, "Paged detail reads must leave the journal unchanged."


@pytest.mark.parametrize(
    "route",
    ["session-detail", "session-agent", "session-pull-requests"],
)
@pytest.mark.parametrize("session_id", [None, "", "x" * 257, "nul\0inside"])
@pytest.mark.asyncio
async def test_query_inspector_routes_reject_invalid_identity(
    tmp_path: pathlib.Path, route: str, session_id: str | None
) -> None:
    """All query aliases enforce the existing bounded raw-ID contract."""
    query = "" if session_id is None else f"?sessionId={quote(session_id, safe='')}"
    async with opened_store(tmp_path) as store:
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get(f"/api/v1/{route}{query}")
            after = (await store.snapshot(), await store.events(0))
    assert response.status_code == 400, "An invalid query ID must fail before lookup."
    assert before == after, "A rejected inspector query must not write the journal."
