"""Operational storage failures must not discard other streamed members."""

import asyncio
import sqlite3
import typing as typ

import msgspec
import pytest
from batch_activity_support import seed_unknown_sessions
from falcon import testing
from sqlalchemy.exc import OperationalError
from storage_support import opened_store

from ishiban.api import create_app
from ishiban.domain import ObservedSession
from ishiban.lazy_activity import LazyActivity
from ishiban.storage import Store

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_one_storage_failure_preserves_other_batch_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locked sidecar for one member leaves its neighbour available."""
    original = Store.remember_activity

    async def remember(
        store: Store, projection: dict[str, object]
    ) -> dict[str, object] | None:
        """Fail one cache write while retaining the ordinary neighbour path.

        Returns
        -------
        dict[str, object] or None
            The saved neighbour projection.

        Raises
        ------
        OperationalError
            If the member is the simulated locked-cache identity.
        """
        if projection["sessionId"] == "locked":
            raise OperationalError("insert", {}, sqlite3.OperationalError("locked"))
        return await original(store, projection)

    async def read(
        _service: LazyActivity, session_id: str, _revision: int
    ) -> ObservedSession:
        """Resolve persisted activity independently of the failing cache write.

        Returns
        -------
        ObservedSession
            Persisted idle activity for the supplied identity.
        """
        await asyncio.sleep(0)
        return ObservedSession(session_id=session_id, source="persisted", state="idle")

    monkeypatch.setattr(Store, "remember_activity", remember)
    monkeypatch.setattr(LazyActivity, "read", read)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["locked", "healthy"])
        baseline = await store.snapshot()
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity", json={"sessionIds": ["locked", "healthy"]}
            )
            frames = [
                msgspec.json.decode(line) for line in response.content.splitlines()
            ]
            by_id = {frame["sessionId"]: frame["session"] for frame in frames}
            assert by_id["locked"] is None, (
                "A failed cache write must become unavailable."
            )
            assert by_id["healthy"]["state"] == "idle", (
                "An independent completed member must still reach the client."
            )
            assert await store.snapshot() == baseline, (
                "The journal must remain unchanged."
            )
