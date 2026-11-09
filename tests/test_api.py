"""The read API serves a consistent cursor and immutable replay projections."""

import typing as typ

import falcon
import pytest
from falcon import testing

from ishiban.api import EventsResource, create_app, parse_cursor
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize(
    ("header", "query", "expected"), [("12", "1", 12), (None, "4", 4), (None, None, 0)]
)
def test_browser_reconnect_cursor_takes_precedence(
    header: str | None, query: str | None, expected: int
) -> None:
    """The original EventSource URL must not rewind automatic reconnects."""
    assert parse_cursor(header, query) == expected, (
        "The browser reconnect header must override its original URL cursor."
    )


@pytest.mark.parametrize(
    "value", ["-1", "1.5", "1e2", "", "\uff19", "9223372036854775808"]
)
def test_invalid_cursor_is_an_explicit_client_error(value: str) -> None:
    """Malformed cursors never become an implicit start-from-zero request."""
    with pytest.raises(falcon.HTTPBadRequest):
        parse_cursor(value, None)


@pytest.mark.asyncio
async def test_snapshot_and_replay_share_the_same_committed_boundary(
    tmp_path: pathlib.Path,
) -> None:
    """A new source-health event is visible after the prior snapshot cursor."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'journal.sqlite3'}", "workspace")
    await store.initialize()
    generation = await store.begin_generation()
    app = create_app(store)
    async with testing.ASGIConductor(app) as conductor:
        snapshot = await conductor.simulate_get("/api/v1/snapshot")
        assert snapshot.status_code == 200, (
            "A migrated journal must expose a readable snapshot."
        )
        baseline = snapshot.json["cursor"]
        await store.health("following", generation)
        stream = EventsResource(store).tail(baseline)
        event = await anext(stream)
        assert event.event == "source", (
            "Collector health updates must use their own source event category."
        )
        assert event.event_id is not None, (
            "Every replay event needs a resumable local journal ID."
        )
        assert int(event.event_id) > baseline, (
            "A post-snapshot update must have a newer local cursor."
        )
        await stream.aclose()
        missing = await conductor.simulate_get("/api/v1/sessions/missing")
        assert missing.status_code == 404, (
            "Missing session identities must remain an explicit not-found response."
        )
        invalid = await conductor.simulate_get("/api/v1/events?after=-1")
        assert invalid.status_code == 400, (
            "Malformed replay cursors must be rejected instead of rewinding."
        )
        assert (await conductor.simulate_get("/ready")).status_code == 200, (
            "Readiness must succeed for a readable migrated database."
        )


@pytest.mark.asyncio
async def test_sse_open_does_not_materialize_a_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opening SSE reads its cursor without decoding every session projection."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'stream.sqlite3'}", "workspace")
    await store.initialize()
    generation = await store.begin_generation()
    baseline = await store.health("following", generation)

    async def unexpected_snapshot() -> dict[str, object]:
        """Reject full projection reads while preserving an async store boundary.

        Raises
        ------
        AssertionError
            If SSE initialization requests a full workspace snapshot.
        """
        await store.current_cursor()
        raise AssertionError

    monkeypatch.setattr(store, "snapshot", unexpected_snapshot)
    stream = EventsResource(store).tail(baseline - 1)
    try:
        event = await anext(stream)
        assert event.event_id == str(baseline), (
            "SSE must replay the event after the requested cursor."
        )
    finally:
        await stream.aclose()
        await store.close()


@pytest.mark.asyncio
async def test_current_cursor_is_read_from_sql_for_its_workspace(
    tmp_path: pathlib.Path,
) -> None:
    """The cursor query returns the bound workspace maximum from SQLite."""
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'cursors.sqlite3'}"
    first = Store(database_url, "first-workspace")
    second = Store(database_url, "second-workspace")
    await first.initialize()
    await second.initialize()
    try:
        await first.begin_generation()
        first_cursor = await first.current_cursor()
        await second.begin_generation()
        second_cursor = await second.current_cursor()

        assert second_cursor > first_cursor, (
            "SQLite must assign increasing IDs across workspace journal rows."
        )
        assert await first.current_cursor() == first_cursor, (
            "A workspace cursor must not include another workspace's event IDs."
        )
        assert await second.current_cursor() == second_cursor, (
            "The SQL cursor must be scoped to the store's workspace."
        )
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_separate_api_reader_opens_existing_schema_without_journal_writes(
    tmp_path: pathlib.Path,
) -> None:
    """A separately started API must open the collector-created database."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'separate.sqlite3'}"
    writer = Store(url, "workspace")
    await writer.initialize()
    await writer.begin_generation()
    before = await writer.snapshot()
    reader = Store(url, "workspace")
    async with testing.ASGIConductor(create_app(reader)) as conductor:
        snapshot = await conductor.simulate_get("/api/v1/snapshot")
        assert snapshot.status_code == 200, (
            "A fresh API process must open an already migrated database."
        )
        assert snapshot.json["cursor"] == before["cursor"], (
            "Opening the read API must not append journal events."
        )
    await writer.close()


@pytest.mark.asyncio
async def test_browser_assets_are_not_reused_after_a_local_rebuild(
    tmp_path: pathlib.Path,
) -> None:
    """Unversioned spike assets must not remain in the browser's heuristic cache."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<main>Ishiban fixture</main>", encoding="utf-8")
    (assets / "app.js").write_text("console.info('fixture');", encoding="utf-8")
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'assets.sqlite3'}", "workspace")
    await store.initialize()
    async with testing.ASGIConductor(create_app(store, assets)) as conductor:
        for path in ("/", "/app.js"):
            response = await conductor.simulate_get(path)
            assert response.status_code == 200, "Local assets must be served."
            assert response.headers.get("cache-control") == "no-store", (
                "Unversioned browser assets must be fetched again after a rebuild."
            )


@pytest.mark.asyncio
async def test_future_cursor_emits_one_reset_and_ends_the_stream(
    tmp_path: pathlib.Path,
) -> None:
    """A cursor from a replaced journal must trigger a fresh client snapshot."""
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'reset.sqlite3'}", "workspace")
    await store.initialize()
    try:
        stream = EventsResource(store).tail(1)
        reset = await anext(stream)
        assert reset.event == "reset_required", (
            "A future cursor must produce a reset rather than wait indefinitely."
        )
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await store.close()
