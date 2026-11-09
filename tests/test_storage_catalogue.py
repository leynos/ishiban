"""Catalogue projection and provenance contracts."""

import typing as typ

import pytest
from storage_support import as_events, as_snapshot, opened_store

from ishiban.domain import CatalogueEntry, PullRequest

if typ.TYPE_CHECKING:
    from pathlib import Path


def entry(*, title: str = "Compiler repair") -> CatalogueEntry:
    """Create one explicit pull-request association for catalogue tests.

    Returns
    -------
    CatalogueEntry
        A draft Plan pull request classified as a building session.
    """
    return CatalogueEntry(
        session_id="s1",
        machine_id="m1",
        title=title,
        archived=False,
        repo_full_name="leynos/ishiban",
        branch_name="initial-spike",
        pull_requests=[
            PullRequest(
                "https://github.com/leynos/ishiban/pull/1", "draft", "Plan: storage"
            )
        ],
        stage="building",
        stage_reason="The associated pull request is a draft without the Plan prefix.",
    )


@pytest.mark.asyncio
async def test_catalogue_updates_emit_only_when_the_projection_changes(
    tmp_path: Path,
) -> None:
    """Repeated identical enrichment is a no-op and never changes evidence."""
    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.begin_generation()
        first_cursor = await store.catalogue(entry(), generation=2)
        duplicate_cursor = await store.catalogue(entry(), generation=2)
        snapshot = as_snapshot(await store.snapshot())
        history = as_events(await store.events(after=0))

    assert first_cursor == 3, (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert duplicate_cursor is None, (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert snapshot["sessions"][0]["stage"] == "building", (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert snapshot["sessions"][0]["lastEvidenceGeneration"] is None, (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert snapshot["sessions"][0]["lastMetadataGeneration"] == 2, (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert len(history) == 3, (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )
    assert history[-1]["source"] == "lody.catalogue", (
        "Repeated identical enrichment is a no-op and never changes evidence."
    )


@pytest.mark.asyncio
async def test_catalogue_refresh_does_not_overwrite_observed_session_state(
    tmp_path: Path,
) -> None:
    """Repository enrichment updates metadata while preserving live evidence."""
    from ishiban.domain import Envelope, ObservedSession, Turn

    async with opened_store(tmp_path) as store:
        await store.begin_generation()
        await store.begin_generation()
        await store.ingest(
            Envelope(
                1,
                "stream-1",
                1,
                1_700_000_000_001,
                "w1",
                "session.changed",
                "s1",
                ObservedSession(
                    session_id="s1",
                    machine_id="m1",
                    title="Compiler repair",
                    archived=False,
                    state="running",
                    source="persisted",
                    freshness="synced",
                    latest_turn=Turn("u1", "running"),
                    active_turns=[Turn("u1", "running")],
                ),
            ),
            generation=2,
        )
        await store.catalogue(entry(title="Catalogue title"), generation=2)
        session = as_snapshot(await store.snapshot())["sessions"][0]

    assert session["state"] == "running", (
        "Repository enrichment updates metadata while preserving live evidence."
    )
    latest_turn = session["latestTurn"]
    assert latest_turn is not None, (
        "Repository enrichment updates metadata while preserving live evidence."
    )
    assert latest_turn["userTurnId"] == "u1", (
        "Repository enrichment updates metadata while preserving live evidence."
    )
    assert session["title"] == "Catalogue title", (
        "Repository enrichment updates metadata while preserving live evidence."
    )
    assert session["repoFullName"] == "leynos/ishiban", (
        "Repository enrichment updates metadata while preserving live evidence."
    )
    assert session["lastEvidenceGeneration"] == 2, (
        "Repository enrichment updates metadata while preserving live evidence."
    )
