"""Generated Store histories protect durable sidecar activity.

The sidecar has no time-based expiry; the lazy-activity request cache has a
separate TTL. These histories vary execution revisions and reopen the database.
"""

import dataclasses as dc
import typing as typ
from pathlib import Path
from tempfile import TemporaryDirectory

import hypothesis
import pytest
from hypothesis import strategies as st
from storage_support import EventOptions, envelope, observed_session

from ishiban.domain import CatalogueEntry
from ishiban.storage import Store


@dc.dataclass(frozen=True, slots=True)
class PendingRead:
    """Hold one completed lookup until the generated history delivers it."""

    projection: dict[str, object]
    execution_revision: int
    label: str


@dc.dataclass(slots=True)
class Expected:
    """Track the user-visible facts without consulting the sidecar's policy."""

    title: str = "Compiler repair"
    stage: str = "unclassified"
    repo: str | None = None
    branch: str | None = None
    state: str = "unknown"
    execution_revision: int = 0
    cached_label: str | None = None
    cached_revision: int = 0
    sequence: int = 1
    metadata_count: int = 0
    lookup_count: int = 0


def _activity_result(pending: PendingRead) -> dict[str, object]:
    """Attach a distinct, known runtime result to one captured journal revision.

    Returns
    -------
    dict[str, object]
        The delayed lookup with a stable turn error for visible attribution.
    """
    return {
        **pending.projection,
        "state": "idle",
        "source": "persisted",
        "freshness": "synced",
        "latestTurn": {
            "userTurnId": pending.label,
            "state": "failed",
            "error": pending.label,
        },
        "activeTurns": [],
        "lastObservedAt": 1_700_000_000_123,
    }


def _catalogue(title: str, metadata_count: int) -> CatalogueEntry:
    """Supply changed metadata without inventing execution evidence.

    Returns
    -------
    CatalogueEntry
        A repository association and title for the fixed test session.
    """
    return CatalogueEntry(
        session_id="s1",
        machine_id="m1",
        title=title,
        archived=False,
        repo_full_name=f"leynos/repo-{metadata_count}",
        branch_name=f"topic-{metadata_count}",
        pull_requests=[],
        stage="planning",
        stage_reason="Catalogue metadata only.",
    )


async def _assert_visible(store: Store, expected: Expected) -> None:
    """Compare a restored view with the independent execution and metadata model."""
    before = await store.snapshot()
    journal = await store.session_projection("s1")
    assert journal is not None, "The seeded session must remain in the journal."
    restored = (await store.restore_activity([journal]))[0]
    assert await store.snapshot() == before, (
        "Restoring sidecar evidence must not change any durable journal fact."
    )
    assert restored["title"] == expected.title, (
        "Lazy runtime must retain the newest catalogue title."
    )
    assert restored["stage"] == expected.stage, (
        "Lazy runtime must retain the newest explicit workflow stage."
    )
    assert restored["repoFullName"] == expected.repo, (
        "Lazy runtime must retain the current repository association."
    )
    assert restored["branchName"] == expected.branch, (
        "Lazy runtime must retain the current branch association."
    )
    assert restored["lastEventId"] == journal["lastEventId"], (
        "A sidecar overlay must retain the current durable revision."
    )
    assert journal.get("lastActivityEventId", 0) == expected.execution_revision, (
        "Only known execution evidence may advance the activity watermark."
    )

    is_cache_valid = (
        expected.state == "unknown"
        and expected.cached_label is not None
        and expected.cached_revision >= expected.execution_revision
    )
    if is_cache_valid:
        latest = restored["latestTurn"]
        assert isinstance(latest, dict), "A cached failed turn must be present."
        latest = typ.cast("dict[str, object]", latest)
        assert restored["state"] == "idle", "The accepted runtime must be visible."
        assert restored["activitySource"] == "lazy", (
            "Restored sidecar evidence must identify its provenance."
        )
        assert latest["error"] == expected.cached_label, (
            "The visible turn must be the last accepted sidecar result."
        )
    else:
        assert restored["state"] == expected.state, (
            "Newer execution or an absent read must leave journal runtime visible."
        )
        assert "activitySource" not in restored, (
            "A superseded cache must not be labelled as current lazy evidence."
        )


@dc.dataclass(slots=True)
class History:
    """Own a live Store and the independent model for one generated history."""

    store: Store
    database_url: str
    generation: int
    expected: Expected = dc.field(default_factory=Expected)
    pending_reads: list[PendingRead] = dc.field(default_factory=list)

    async def apply(self, action: str) -> None:
        """Apply one history action and check its visible prefix.

        For example, a delayed lookup after a newer execution is rejected.
        """
        match action:
            case "capture":
                await self._capture()
            case "resolve_old" | "resolve_new":
                await self._resolve(is_oldest=action == "resolve_old")
            case "metadata":
                await self._metadata()
            case "execution" | "reset":
                await self._observe(is_execution=action == "execution")
            case "reopen":
                await self._reopen()
        await _assert_visible(self.store, self.expected)

    async def _capture(self) -> None:
        """Retain one unknown projection for a later, possibly stale delivery."""
        if self.expected.state != "unknown":
            return
        captured = await self.store.session_projection("s1")
        assert captured is not None, "The seeded session must be capturable."
        self.expected.lookup_count += 1
        self.pending_reads.append(
            PendingRead(
                captured,
                self.expected.execution_revision,
                f"lookup-{self.expected.lookup_count}",
            )
        )

    async def _resolve(self, *, is_oldest: bool) -> None:
        """Deliver one lookup, checking its sidecar and journal effects.

        For example, oldest-first delivery can race a newer execution.
        """
        if not self.pending_reads:
            return
        index = 0 if is_oldest else -1
        pending = self.pending_reads.pop(index)
        before = await self.store.snapshot()
        events_before = await self.store.events(0)
        result = await self.store.remember_activity(_activity_result(pending))
        is_accepted = (
            self.expected.state == "unknown"
            and pending.execution_revision == self.expected.execution_revision
        )
        if is_accepted:
            self.expected.cached_label = pending.label
            revision = before["cursor"]
            assert isinstance(revision, int), "The durable cursor must be numeric."
            self.expected.cached_revision = revision
            assert result is not None, "A current lookup must be accepted."
            assert result["title"] == self.expected.title, (
                "An accepted read must retain the current metadata title."
            )
            assert result["activitySource"] == "lazy", (
                "Accepted runtime must identify its lazy source."
            )
        else:
            assert result is None, "A read from older execution must be rejected."
        assert await self.store.snapshot() == before, (
            "A lazy read must not write the journal."
        )
        assert await self.store.events(0) == events_before, (
            "Lazy reads must not append source or metadata events."
        )

    async def _metadata(self) -> None:
        """Change only catalogue metadata, leaving execution evidence intact."""
        self.expected.metadata_count += 1
        self.expected.title = f"Catalogue {self.expected.metadata_count}"
        self.expected.stage = "planning"
        self.expected.repo = f"leynos/repo-{self.expected.metadata_count}"
        self.expected.branch = f"topic-{self.expected.metadata_count}"
        await self.store.catalogue(
            _catalogue(self.expected.title, self.expected.metadata_count),
            self.generation,
        )

    async def _observe(self, *, is_execution: bool) -> None:
        """Append known or unknown persisted evidence to the real journal.

        For example, a running observation followed by unknown leaves a newer
        execution watermark while the session again permits lazy reads.
        """
        self.expected.sequence += 1
        self.expected.state = "running" if is_execution else "unknown"
        self.expected.title = "Compiler repair"
        cursor = await self.store.ingest(
            envelope(
                self.expected.sequence,
                options=EventOptions(
                    session=observed_session(
                        state=self.expected.state,
                        source="persisted",
                    )
                ),
            ),
            self.generation,
        )
        if is_execution:
            self.expected.execution_revision = cursor

    async def _reopen(self) -> None:
        """Reopen both databases and prove no durable journal change occurred."""
        before = await self.store.snapshot()
        await self.store.close()
        self.store = Store(self.database_url, "w1")
        await self.store.initialize()
        assert await self.store.snapshot() == before, (
            "Reopening must not rewrite the journal."
        )


@hypothesis.example(actions=["capture", "metadata", "reopen", "resolve_old", "reopen"])
@hypothesis.example(
    actions=[
        "capture",
        "execution",
        "reset",
        "metadata",
        "reopen",
        "resolve_old",
    ]
)
@hypothesis.example(
    actions=[
        "capture",
        "resolve_old",
        "execution",
        "reset",
        "capture",
        "resolve_new",
        "reopen",
    ]
)
@hypothesis.example(
    actions=[
        "capture",
        "execution",
        "reset",
        "capture",
        "resolve_new",
        "resolve_old",
        "reopen",
    ]
)
@hypothesis.given(
    actions=st.lists(
        st.sampled_from([
            "capture",
            "resolve_old",
            "resolve_new",
            "metadata",
            "execution",
            "reset",
            "reopen",
        ]),
        min_size=1,
        max_size=10,
    )
)
@hypothesis.settings(max_examples=30, deadline=None)
@pytest.mark.asyncio
async def test_sidecar_history_preserves_current_metadata_and_execution(
    actions: list[str],
) -> None:
    """Delayed reads and reopenings cannot replace newer journal evidence."""
    with TemporaryDirectory() as directory:
        database_url = f"sqlite+aiosqlite:///{Path(directory) / 'ishiban.sqlite3'}"
        store = Store(database_url, "w1")
        await store.initialize()
        history = History(store, database_url, generation=0)
        try:
            generation = await store.begin_generation()
            seed = await store.ingest(
                envelope(
                    1,
                    options=EventOptions(
                        session=observed_session(state="unknown", source="metadata")
                    ),
                ),
                generation,
            )
            history.generation = generation
            assert seed > 0, "The seed observation must enter the journal."
            await _assert_visible(store, history.expected)
            for action in actions:
                await history.apply(action)
        finally:
            await history.store.close()
