"""Carry a validated observer timestamp through storage to the React inspector."""

import json
import typing as typ

import msgspec
import pytest
from bun_test_capture import capture_bun_test_output
from storage_support import as_snapshot, opened_store

from ishiban.protocol import MAX_OBSERVED_AT_MS, StreamPosition, decode_event

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_maximum_observer_timestamp_survives_snapshot_and_renders_in_bun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The date-limit timestamp reaches the inspector after journal projection."""
    raw = msgspec.json.encode({
        "version": 1,
        "streamId": "timestamp-stream",
        "sequence": 1,
        "observedAt": MAX_OBSERVED_AT_MS,
        "workspaceId": "w1",
        "type": "session.changed",
        "sessionId": "timestamp-session",
        "session": {
            "sessionId": "timestamp-session",
            "machineId": "machine",
            "title": "Timestamp boundary",
            "archived": False,
            "state": "running",
            "source": "persisted",
            "freshness": "synced",
            "activeTurns": [],
        },
    })
    event = decode_event(raw, "w1", StreamPosition())

    async with opened_store(tmp_path) as store:
        generation = await store.begin_generation()
        await store.ingest(event, generation=generation, raw=raw)
        session = as_snapshot(await store.snapshot())["sessions"][0]

    assert session["sessionId"] == "timestamp-session", (
        "The stored session must remain identifiable after observation."
    )
    assert session["lastObservedAt"] == MAX_OBSERVED_AT_MS, (
        "The protocol timestamp must survive the durable public projection."
    )
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps(session), encoding="utf-8")
    monkeypatch.setenv("ISHIBAN_OBSERVED_TIMESTAMP_SESSION", str(session_path))
    result = json.loads(
        await capture_bun_test_output(
            tmp_path,
            test_file="tests/observed-timestamp-contract.test.tsx",
            variable="ISHIBAN_OBSERVED_TIMESTAMP_RESULT",
        )
    )

    assert result["sessionId"] == "timestamp-session", (
        "The UI must render the same stored session."
    )
    assert result["lastObservedAt"] == MAX_OBSERVED_AT_MS, (
        "The rendered boundary value must match the committed observation."
    )
    assert result["visibleTimestamp"] != "Timestamp unavailable", (
        "The largest supported protocol timestamp must remain renderable."
    )
