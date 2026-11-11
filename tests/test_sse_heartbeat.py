"""SSE heartbeats preserve replay cursors and restart their idle interval."""

import asyncio
import math
import typing as typ
from types import SimpleNamespace

import pytest
from storage_support import opened_store

from ishiban import api
from ishiban.api import EventsResource

if typ.TYPE_CHECKING:
    from pathlib import Path

    from ishiban.storage import Store


class ControlledPolls:
    """Bound SSE idle polling while retaining real asynchronous store operations.

    Example
    -------
    clock = ControlledPolls(store, generation)
    monkeypatch.setattr(api, "asyncio", SimpleNamespace(sleep=clock.sleep))
    """

    def __init__(self, store: Store, generation: int) -> None:
        """Capture real sleep before replacing only the API module's binding."""
        self.store = store
        self.generation = generation
        self.real_sleep = asyncio.sleep
        self.count = 0
        self.inject_at: int | None = None
        self.injected_cursor: int | None = None

    async def sleep(self, delay: float) -> None:
        """Yield immediately for a poll, failing after 220 owned polls."""
        if math.isclose(delay, 0.25):
            self.count += 1
            if self.count > 220:
                pytest.fail("An SSE frame did not arrive within bounded idle polls.")
            if self.count == self.inject_at:
                self.injected_cursor = await self.store.health(
                    "following", self.generation
                )
            await self.real_sleep(0)
        else:
            await self.real_sleep(delay)


@pytest.mark.asyncio
async def test_idle_heartbeats_repeat_and_source_activity_restarts_the_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quiet stream keeps its cursor while a source event earns a fresh interval."""
    async with asyncio.timeout(10), opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        baseline = await store.current_cursor()
        polls = ControlledPolls(store, generation)
        monkeypatch.setattr(api, "asyncio", SimpleNamespace(sleep=polls.sleep))
        assert asyncio.sleep is polls.real_sleep, (
            "The SSE poll driver must not replace the shared asyncio sleep function."
        )
        stream = EventsResource(store).tail(baseline)
        try:
            first = await anext(stream)
            first_interval = polls.count
            assert first.serialize() == b": heartbeat\n\n", (
                "An idle connection needs a comment without event or ID fields."
            )
            assert first.event_id is None, "A heartbeat must not be resumable."
            assert 59 <= first_interval <= 60, (
                "The first comment needs a full idle interval."
            )
            assert await store.current_cursor() == baseline, (
                "A heartbeat must not append to the durable source journal."
            )

            second = await anext(stream)
            assert second.comment == "heartbeat", (
                "A still-idle stream needs another comment."
            )
            assert second.event_id is None, (
                "Repeated comments must not carry replay IDs."
            )
            assert polls.count - first_interval == 60, (
                "A repeated heartbeat must wait a complete new idle interval."
            )
            assert await store.current_cursor() == baseline, (
                "Repeated comments must leave the durable cursor unchanged."
            )

            polls.inject_at = polls.count + 20
            source = await anext(stream)
            assert polls.injected_cursor is not None, (
                "A source event must be committed."
            )
            assert source.event == "source", (
                "Journal activity needs the source category."
            )
            assert source.event_id == str(polls.injected_cursor), (
                "Journal activity needs its own resumable event identity."
            )
            assert await store.current_cursor() == polls.injected_cursor, (
                "The emitted source event must be the only new committed journal item."
            )

            source_poll = polls.count
            after_source = await anext(stream)
            assert after_source.comment == "heartbeat", (
                "The next idle frame needs a comment."
            )
            assert after_source.event_id is None, (
                "A later comment must not carry an ID."
            )
            assert 59 <= polls.count - source_poll <= 60, (
                "A source event must restart the full idle interval."
            )
            assert await store.current_cursor() == polls.injected_cursor, (
                "The post-activity heartbeat must not advance the source cursor."
            )
        finally:
            await stream.aclose()
