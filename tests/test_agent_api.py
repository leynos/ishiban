"""The inspector API exposes only whitelisted agent metadata for known sessions."""

import typing as typ
from unittest import mock

import pytest
from falcon import testing
from storage_support import EventOptions, envelope, observed_session, opened_store

from ishiban.api import create_app
from ishiban.domain import CatalogueEntry, PullRequest
from ishiban.pull_request_details import PullRequestTitles
from ishiban.session_agent import AgentDetails, SessionAgentDetails

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_agent_details_are_scoped_and_do_not_change_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent lookup does not expose configuration contents or create source events."""
    reader = mock.AsyncMock(return_value=AgentDetails("codex", "config-1", "My agent"))
    monkeypatch.setattr(SessionAgentDetails, "read", reader)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(
            envelope(1, options=EventOptions(session=observed_session())), generation
        )
        before = await store.snapshot()
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get("/api/v1/sessions/s1/agent")
            missing = await conductor.simulate_get("/api/v1/sessions/missing/agent")
            assert response.json["workspaceId"] == "w1", (
                "Scope the labels to the workspace."
            )
            assert response.json["sessionId"] == "s1", (
                "Identify the requested Lody session."
            )
            agent = response.json["agent"]
            assert set(agent) == {
                "agentType",
                "configurationId",
                "configurationName",
            }, "Only public agent labels and identities may leave the API."
            assert agent["agentType"] == "codex", "Return the observed agent type."
            assert agent["configurationId"] == "config-1", (
                "Retain the configuration identity."
            )
            assert agent["configurationName"] == "My agent", "Return its display name."
            assert await store.snapshot() == before, (
                "Agent lookup must leave the journal untouched."
            )
            assert missing.status_code == 404, (
                "Missing sessions must not trigger a CLI lookup."
            )
        reader.assert_awaited_once_with("s1")


@pytest.mark.asyncio
async def test_missing_merged_pr_titles_are_inspector_only_enrichment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Merged PR names resolve without rewriting stage or journal metadata."""
    url = "https://github.com/example/project/pull/123"
    reader = mock.AsyncMock(return_value={url: "A merged PR name"})
    monkeypatch.setattr(PullRequestTitles, "read", reader)
    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.catalogue(
            CatalogueEntry(
                session_id="s1",
                machine_id="machine",
                title="Session subtitle",
                archived=False,
                repo_full_name="example/project",
                branch_name="main",
                pull_requests=[PullRequest(url, "merged")],
                stage="merged",
                stage_reason="The PR was merged.",
            ),
            generation,
        )
        before = await store.snapshot()
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_get("/api/v1/sessions/s1/pull-requests")
            missing = await conductor.simulate_get(
                "/api/v1/sessions/missing/pull-requests"
            )
            assert response.json["titles"] == {url: "A merged PR name"}, (
                "Terminal PRs need display names as well as links."
            )
            assert await store.snapshot() == before, (
                "Lazy PR names must not alter classification or durable events."
            )
            assert missing.status_code == 404, "Missing sessions must not reach GitHub."
        reader.assert_awaited_once_with([url])
