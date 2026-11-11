"""Keep read-only lookup diagnostics useful without logging source payloads."""

import asyncio
import json
import typing as typ
from unittest import mock

import msgspec
import pytest
from sqlalchemy.exc import OperationalError
from storage_support import opened_store

from ishiban.cached_lody_reads import CachedLodyReads, CachedReadPolicy
from ishiban.protocol import ProtocolError
from ishiban.session_recency_api import SessionRecencyResource
from ishiban.session_show import SessionShowReader

if typ.TYPE_CHECKING:
    from pathlib import Path

POLICY = CachedReadPolicy(4, 1, 300.0, 30.0)
PRIVATE = "DO_NOT_LOG_SOURCE_DETAILS"


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (OSError(PRIVATE), "cli"),
        (TimeoutError(PRIVATE), "deadline"),
        (ProtocolError(PRIVATE), "protocol"),
        (msgspec.DecodeError(PRIVATE), "protocol"),
    ],
)
@pytest.mark.asyncio
async def test_metadata_failure_categories_are_redacted_and_cached(
    caplog: pytest.LogCaptureFixture, error: Exception, category: str
) -> None:
    """Failures expose fixed categories once without IDs or exception messages."""
    reader = CachedLodyReads[str, str](
        POLICY, lambda: 0.0, mock.AsyncMock(side_effect=error)
    )
    try:
        assert await reader.read(PRIVATE) is None, "Failed reads stay unavailable."
        assert await reader.read(PRIVATE) is None, "Negative cache hits stay quiet."
    finally:
        await reader.close()

    records = [
        record
        for record in caplog.records
        if record.name == "ishiban.cached_lody_reads"
    ]
    assert [record.getMessage() for record in records] == [
        f"Lody metadata unavailable category={category}"
    ], "Only the first failed lookup should emit its bounded diagnostic."
    assert PRIVATE not in caplog.text, "Diagnostics must not expose IDs or error text."
    assert all(record.exc_info is None for record in records), (
        "A traceback must not reintroduce the redacted provider error."
    )


@pytest.mark.asyncio
async def test_capacity_diagnostic_does_not_discard_the_admitted_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Capacity rejection stays separate from the successful in-flight sibling."""
    started = asyncio.Event()
    release = asyncio.Event()
    now = [0.0]

    async def load(_key: str) -> str | None:
        """Hold the single slot until the test releases its admitted read.

        Returns
        -------
        str or None
            The resolved test value after its release signal.
        """
        started.set()
        await release.wait()
        return "resolved"

    reader = CachedLodyReads(POLICY, lambda: now[0], load)
    admitted = asyncio.create_task(reader.read("admitted"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        for key in (PRIVATE, "second-private-id", "third-private-id"):
            assert await reader.read(key) is None, (
                "A full cache owner rejects new work."
            )
        now[0] = 30.0
        assert await reader.read("fourth-private-id") is None, (
            "Admission remains bounded when the warning interval expires."
        )
        release.set()
        assert await admitted == "resolved", (
            "Rejected work must not cancel its sibling."
        )
    finally:
        await reader.close()
        await asyncio.gather(admitted, return_exceptions=True)

    records = [
        record.getMessage()
        for record in caplog.records
        if record.name == "ishiban.cached_lody_reads"
    ]
    assert records == [
        "Lody metadata unavailable category=capacity",
        "Lody metadata unavailable category=capacity suppressed=2",
    ], "The reader emits one redacted capacity warning per 30-second interval."
    assert all("private-id" not in record for record in records), (
        "Rejected identities must remain private."
    )


@pytest.mark.asyncio
async def test_recency_storage_failure_has_a_redacted_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Storage failures retain the unavailable frame without exposing SQL text."""
    async with opened_store(tmp_path) as store:
        monkeypatch.setattr(
            store,
            "session_projection",
            mock.AsyncMock(
                side_effect=OperationalError(PRIVATE, {}, Exception(PRIVATE))
            ),
        )
        reader = SessionShowReader(store.workspace_id, "leynos")
        try:
            resource = SessionRecencyResource(store, reader)
            frame = json.loads(await resource._resolve_one(PRIVATE))
        finally:
            await reader.close()

    assert frame["outcome"] == "unavailable", (
        "Storage failure must stay a partial result."
    )
    assert "category=storage" in caplog.text, (
        "Storage failures need a distinct category."
    )
    assert PRIVATE not in caplog.text, (
        "SQL and session data must not reach diagnostics."
    )
