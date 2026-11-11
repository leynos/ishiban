"""Observer retries preserve finite source streams through real journal writes."""

import asyncio
import functools
import pathlib
import sqlite3
import tempfile
import types
import typing as typ

import msgspec
import pytest
import storage_support
from hypothesis import example, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from test_collector_startup import _controlled_child
from test_protocol import event_line

from ishiban import collector as observation
from ishiban.protocol import ProtocolError
from ishiban.storage.models import source_events

if typ.TYPE_CHECKING:
    from ishiban.domain import Envelope
    from ishiban.storage import Store


class IngestionProbe:
    """Apply generated write faults while checking the reader's ACK boundary."""

    def __init__(self, store: Store, plans: list[tuple[str, int, int]]) -> None:
        """Build one finite valid stream with unknown private v1 payload fields."""
        self.records = [
            event_line(
                workspaceId="w1",
                sequence=sequence,
                observedAt=sequence,
                type=kind,
                sessionId="s1",
                session={"sessionId": "s1", "state": "running", "source": "persisted"},
                unknownV1={"record": sequence},
            )
            + b"\n"
            for sequence, (kind, _, _) in enumerate(plans, start=1)
        ]
        self.reader = asyncio.StreamReader()
        self.reader.feed_data(b"".join(self.records))
        self.reader.feed_eof()
        self.original_readline = self.reader.readline
        self.original_ingest = store.ingest
        self.remaining = [[before, after] for _, before, after in plans]
        self.attempts: list[list[bytes | None]] = [[] for _ in plans]
        self.acknowledged = 0
        self.read_calls = 0

    async def readline(self) -> bytes:
        """Reject any read ahead of the preceding store acknowledgement.

        Returns
        -------
        bytes
            The next buffered observer line, or EOF.
        """
        assert self.read_calls == self.acknowledged, (
            "Collector must await the current record's store acknowledgement."
        )
        self.read_calls += 1
        return await self.original_readline()

    async def ingest(
        self, event: Envelope, generation: int, *, raw: bytes | None = None
    ) -> int:
        """Apply generated failures before or after the real journal commit.

        Returns
        -------
        int
            The real cursor after an acknowledged write.

        Raises
        ------
        OperationalError
            On a generated precommit or uncertain postcommit attempt.
        """
        index = event.sequence - 1
        self.attempts[index].append(raw)
        if self.remaining[index][0]:
            self.remaining[index][0] -= 1
            raise OperationalError("ingest", {}, sqlite3.OperationalError())
        if self.remaining[index][1]:
            self.remaining[index][1] -= 1
            await self.original_ingest(event, generation, raw=raw)
            raise OperationalError("ingest", {}, sqlite3.OperationalError())
        cursor = await self.original_ingest(event, generation, raw=raw)
        self.acknowledged += 1
        return cursor


async def _yield_retry(delay: float) -> None:
    """Yield generated retries without waiting for their wall-clock duration."""
    assert 1 <= delay <= 30, "Every retry delay must stay within its cap."
    await asyncio.sleep(0)


async def _committed_records(store: Store) -> list[tuple[int, object]]:
    """Read private source rows to check upstream order and raw-field retention.

    Returns
    -------
    list[tuple[int, object]]
        Ordered source sequence and decoded private payload pairs.
    """
    statement = (
        select(source_events.c.sequence, source_events.c.payload_json)
        .where(
            source_events.c.workspace_id == "w1",
            source_events.c.stream_id == "stream",
        )
        .order_by(source_events.c.id)
    )
    async with store._engine.connect() as connection:
        rows = (await connection.execute(statement)).all()
    return [(sequence, msgspec.json.decode(payload)) for sequence, payload in rows]


@example(plans=[("snapshot", 0, 0)])
@example(plans=[("snapshot", 2, 2), ("session.changed", 1, 2)])
@given(
    plans=st.lists(
        st.tuples(
            st.sampled_from(("snapshot", "session.changed")),
            st.integers(min_value=0, max_value=2),
            st.integers(min_value=0, max_value=2),
        ),
        min_size=1,
        max_size=6,
    )
)
@settings(max_examples=25, deadline=None)
@pytest.mark.asyncio
async def test_observer_stream_retry_preserves_raw_order_and_exactly_once_commit(
    plans: list[tuple[str, int, int]],
) -> None:
    """Precommit and uncertain postcommit failures cannot consume a later line."""
    with tempfile.TemporaryDirectory(prefix="ishiban-property-") as case_dir:
        async with storage_support.opened_store(pathlib.Path(case_dir)) as store:
            probe = IngestionProbe(store, plans)
            collector = observation.Collector(store, "leynos", github=False)
            collector.generation = await store.begin_generation()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(probe.reader, "readline", probe.readline)
                patch.setattr(store, "ingest", probe.ingest)
                patch.setattr(
                    observation,
                    "child",
                    functools.partial(_controlled_child, stdout=probe.reader),
                )
                patch.setattr(
                    observation,
                    "asyncio",
                    types.SimpleNamespace(sleep=_yield_retry),
                )
                with pytest.raises(ProtocolError, match="Observer exited"):
                    await collector._follow()
            assert probe.acknowledged == len(probe.records), (
                "Every generated record must receive a store acknowledgement."
            )
            assert probe.read_calls == len(probe.records) + 1, (
                "The observer must read each line once and then observe EOF."
            )
            for index, (_, before, after) in enumerate(plans):
                assert probe.attempts[index] == [probe.records[index]] * (
                    before + after + 1
                ), "Every retry must use the exact original raw line."
            assert await _committed_records(store) == [
                (sequence, msgspec.json.decode(record))
                for sequence, record in enumerate(probe.records, start=1)
            ], "The journal must preserve each source record once, in stream order."
