"""Test durable runtime restoration without changing journal projections."""

import asyncio
import pathlib
import sqlite3
import typing as typ

import msgspec
import pytest
from sqlalchemy.engine import URL

from ishiban.storage import activity_cache
from ishiban.storage.activity_cache import ActivityCache


def _journal_url(database_path: pathlib.Path) -> str:
    """Build an async SQLite URL through SQLAlchemy's URL constructor.

    Returns
    -------
    str
        A journal URL whose sidecar is a sibling database file.
    """
    return URL.create(
        "sqlite+aiosqlite",
        database=str(pathlib.Path(database_path)),
    ).render_as_string(hide_password=False)


def _projection(session_id: str = "s1", **overrides: object) -> dict[str, object]:
    """Build one unknown journal projection with runtime and metadata fields.

    Returns
    -------
    dict of str to object
        A projection suitable for cache persistence and restoration tests.
    """
    projection: dict[str, object] = {
        "sessionId": session_id,
        "state": "unknown",
        "source": "persisted",
        "freshness": "synced",
        "latestTurn": None,
        "activeTurns": [],
        "lastObservedAt": None,
        "lastEventId": 10,
        "removed": False,
        "title": "Journal title",
        "generation": 4,
        "lastMetadataGeneration": 2,
        "pullRequests": [{"title": "Journal PR"}],
    }
    projection.update(overrides)
    return projection


async def _initialized_cache(
    journal_url: str,
    workspace_id: str = "w1",
) -> ActivityCache:
    """Create and initialize one cache for a sidecar-backed test database.

    Returns
    -------
    ActivityCache
        A ready cache whose engine must be closed by the test.
    """
    cache = ActivityCache(journal_url, workspace_id)
    await cache.initialize()
    return cache


def _stored_runtime_fields(sidecar_path: pathlib.Path) -> dict[str, object]:
    """Read one encoded runtime value from the cache-only SQLite table.

    Returns
    -------
    dict of str to object
        Decoded runtime fields stored for session ``s1``.

    Raises
    ------
    AssertionError
        If no row was persisted for the test session.
    """
    with sqlite3.connect(sidecar_path) as connection:
        row = connection.execute(
            "SELECT runtime_json FROM activity_runtime_cache WHERE session_id = ?",
            ("s1",),
        ).fetchone()
    if row is None:
        raise AssertionError
    return msgspec.json.decode(row[0], type=dict[str, object])


@pytest.mark.asyncio
async def test_runtime_round_trips_from_sidecar_without_metadata_or_journal_writes(
    tmp_path: pathlib.Path,
) -> None:
    """A restart restores runtime errors while retaining current journal metadata."""
    journal_path = tmp_path / "journal.sqlite3"
    journal_url = _journal_url(journal_path)
    original_runtime = _projection(
        state="running",
        latestTurn={
            "userTurnId": "turn-1",
            "state": "failed",
            "error": "compiler exited with status 2",
        },
        activeTurns=[{"userTurnId": "turn-1", "state": "failed"}],
        lastObservedAt=1_700_000_000_123,
    )
    cache = await _initialized_cache(journal_url)
    try:
        await cache.remember(original_runtime)
    finally:
        await cache.close()

    sidecar_path = pathlib.Path(f"{journal_path}.activity.sqlite3")
    assert await asyncio.to_thread(sidecar_path.exists), (
        "The cache must persist in its sibling sidecar."
    )
    assert not await asyncio.to_thread(journal_path.exists), (
        "Cache writes must leave the journal database alone."
    )
    stored_fields = await asyncio.to_thread(_stored_runtime_fields, sidecar_path)
    assert set(stored_fields) == set(activity_cache.RUNTIME_FIELDS), (
        "The sidecar must contain only the approved runtime fields."
    )
    assert "title" not in stored_fields, "Titles must not enter the runtime cache."
    assert "pullRequests" not in stored_fields, (
        "Pull request metadata must not enter the runtime cache."
    )

    reopened = await _initialized_cache(journal_url)
    try:
        current = _projection(
            state="unknown",
            lastEventId=19,
            title="Refreshed journal title",
            generation=8,
            lastMetadataGeneration=7,
            pullRequests=[{"title": "Refreshed PR"}],
        )
        restored = (await reopened.merge([current]))[0]
    finally:
        await reopened.close()
    assert restored["state"] == "running", (
        "A reopened cache must restore the last known runtime state."
    )
    latest_turn = typ.cast("dict[str, object]", restored["latestTurn"])
    assert latest_turn["error"] == "compiler exited with status 2", (
        "The latest turn's error must survive the sidecar round trip."
    )
    assert restored["lastObservedAt"] == 1_700_000_000_123, (
        "The latest observation time must survive the sidecar round trip."
    )
    assert restored["title"] == "Refreshed journal title", (
        "Restoration must preserve the current journal title."
    )
    assert restored["pullRequests"] == [{"title": "Refreshed PR"}], (
        "Restoration must preserve current pull request metadata."
    )
    assert restored["lastEventId"] == 19, (
        "Restoration must preserve the current durable event revision."
    )
    assert restored["generation"] == 8, (
        "Restoration must preserve the current collector generation."
    )
    assert restored["activitySource"] == "lazy", (
        "A restored runtime projection must be marked as lazy activity."
    )


@pytest.mark.asyncio
async def test_older_remember_does_not_replace_a_newer_cached_revision(
    tmp_path: pathlib.Path,
) -> None:
    """A delayed older lookup cannot regress the sidecar's runtime state."""
    cache = await _initialized_cache(_journal_url(tmp_path / "journal.sqlite3"))
    try:
        await cache.remember(
            _projection(
                state="running",
                lastEventId=14,
                latestTurn={"userTurnId": "new", "state": "failed", "error": "new"},
            )
        )
        await cache.remember(
            _projection(
                state="waiting",
                lastEventId=12,
                latestTurn={"userTurnId": "old", "state": "running"},
            )
        )
        restored = (await cache.merge([_projection(lastEventId=15)]))[0]
    finally:
        await cache.close()
    assert restored["state"] == "running", (
        "A stale base revision must not overwrite the newer cached state."
    )
    latest_turn = typ.cast("dict[str, object]", restored["latestTurn"])
    assert latest_turn["error"] == "new", (
        "The latest error must remain paired with its newer cached revision."
    )


@pytest.mark.asyncio
async def test_merge_is_workspace_scoped_and_unknown_persisted_state_is_eligible(
    tmp_path: pathlib.Path,
) -> None:
    """Persisted unknown projections restore only within their workspace."""
    journal_url = _journal_url(tmp_path / "journal.sqlite3")
    source = await _initialized_cache(journal_url, "w1")
    try:
        await source.remember(_projection(state="idle"))
    finally:
        await source.close()

    same_workspace = await _initialized_cache(journal_url, "w1")
    other_workspace = await _initialized_cache(journal_url, "w2")
    try:
        restored = (await same_workspace.merge([_projection(source="persisted")]))[0]
        isolated = (await other_workspace.merge([_projection(source="persisted")]))[0]
    finally:
        await same_workspace.close()
        await other_workspace.close()
    assert restored["state"] == "idle", (
        "An unknown persisted-source projection must receive cached runtime."
    )
    assert restored["activitySource"] == "lazy", (
        "Restored persisted runtime must carry the lazy source marker."
    )
    assert isolated == _projection(source="persisted"), (
        "A different workspace must not see another workspace's cache row."
    )


@pytest.mark.asyncio
async def test_merge_skips_known_removed_and_newer_activity_projections(
    tmp_path: pathlib.Path,
) -> None:
    """Known activity, tombstones, and newer events always win over cache."""
    cache = await _initialized_cache(_journal_url(tmp_path / "journal.sqlite3"))
    try:
        await cache.remember(
            _projection(
                state="running",
                lastEventId=10,
                latestTurn={"userTurnId": "cached", "state": "failed"},
            )
        )
        eligible = _projection(lastEventId=12, lastActivityEventId=10)
        newer_event = _projection(lastEventId=12, lastActivityEventId=11)
        known_state = _projection(state="waiting")
        removed = _projection(removed=True)
        merged = await cache.merge([eligible, newer_event, known_state, removed])
    finally:
        await cache.close()
    assert merged[0]["state"] == "running", (
        "An unknown projection without a newer activity event must restore cache."
    )
    assert merged[0]["activitySource"] == "lazy", (
        "An eligible cache overlay must identify its source."
    )
    assert merged[1] == newer_event, (
        "A real activity event newer than the cache base must remain untouched."
    )
    assert merged[2] == known_state, "A known incoming state must always win."
    assert merged[3] == removed, "A removed session must never receive lazy activity."


@pytest.mark.asyncio
async def test_cache_prunes_oldest_rows_per_workspace(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sidecar retains only the configured newest workspace rows."""
    monkeypatch.setattr(activity_cache, "MAX_ROWS_PER_WORKSPACE", 2)
    save_times = iter((100, 200, 300))
    monkeypatch.setattr(activity_cache.time, "time_ns", lambda: next(save_times))
    cache = await _initialized_cache(_journal_url(tmp_path / "journal.sqlite3"))
    try:
        await cache.remember(_projection("s1", state="idle"))
        await cache.remember(_projection("s2", state="running"))
        await cache.remember(_projection("s3", state="waiting"))
        restored = await cache.merge([
            _projection("s1"),
            _projection("s2"),
            _projection("s3"),
        ])
    finally:
        await cache.close()
    assert "activitySource" not in restored[0], (
        "The oldest row must be pruned when the workspace cache is full."
    )
    assert restored[1]["state"] == "running", (
        "A retained cache row must still restore runtime activity."
    )
    assert restored[2]["state"] == "waiting", (
        "The newest cache row must remain available."
    )


@pytest.mark.asyncio
async def test_unknown_activity_is_not_remembered(
    tmp_path: pathlib.Path,
) -> None:
    """The sidecar accepts only successful known runtime states."""
    cache = await _initialized_cache(_journal_url(tmp_path / "journal.sqlite3"))
    try:
        with pytest.raises(ValueError, match=r".*"):
            await cache.remember(_projection(state="unknown"))
        result = (await cache.merge([_projection()]))[0]
    finally:
        await cache.close()
    assert result == _projection(), (
        "An unknown observation must not create a restorable cache row."
    )


@pytest.mark.parametrize(
    "memory_url",
    [
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///file:shared-cache?mode=memory&cache=shared&uri=true",
    ],
    ids=["private-memory", "named-memory"],
)
@pytest.mark.asyncio
async def test_memory_journal_urls_keep_an_independent_memory_cache(
    memory_url: str,
) -> None:
    """Memory journal URLs do not turn the cache into a shared/file database."""
    first = await _initialized_cache(memory_url)
    try:
        await first.remember(_projection(state="running"))
    finally:
        await first.close()
    reopened = await _initialized_cache(memory_url)
    try:
        restored = (await reopened.merge([_projection()]))[0]
    finally:
        await reopened.close()
    assert restored == _projection(), (
        "A fresh memory cache must not inherit another engine's activity rows."
    )
