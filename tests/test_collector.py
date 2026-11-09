"""A real fake-CLI boundary exercises catalogue and observer lifecycle together."""

import asyncio
import pathlib
import sys

import msgspec
import pytest

from ishiban.collector import Collector
from ishiban.lody import read_catalogue
from ishiban.storage import Store


class CollectorStatus(msgspec.Struct):
    """Only source health is relevant to this boundary assertion."""

    state: str


class SessionStatus(msgspec.Struct, rename="camel"):
    """A narrow semantic projection asserted after catalogue reconciliation."""

    repo_full_name: str
    stage: str
    state: str


class SnapshotStatus(msgspec.Struct):
    """Typed public response without incidental timestamps or host identifiers."""

    collector: CollectorStatus
    sessions: list[SessionStatus]


def fake_lody(directory: pathlib.Path) -> pathlib.Path:
    """Write a hanging fake CLI from the non-secret fixture corpus.

    Returns
    -------
    pathlib.Path
        Executable that emits one complete response before lingering.
    """
    fixtures = pathlib.Path(__file__).parent / "fixtures"
    catalogue = (fixtures / "lody-catalogue.json").read_text()
    events = (fixtures / "lody-observer.jsonl").read_text()
    executable = directory / "fake-lody"
    executable.write_text(
        f"#!{sys.executable}\nimport sys, time\n"
        f"catalogue = {catalogue!r}\nevents = {events!r}\n"
        "print(catalogue if 'list' in sys.argv else events, end='', flush=True)\n"
        "time.sleep(120)\n"
    )
    executable.chmod(0o700)
    return executable


@pytest.mark.asyncio
async def test_collector_ingests_observer_and_reaps_it_on_cancellation(
    tmp_path: pathlib.Path,
) -> None:
    """The command boundary journals a baseline and exposes source health."""
    executable = fake_lody(tmp_path)
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'collector.sqlite3'}", "workspace")
    await store.initialize()
    initial = await read_catalogue("leynos", str(executable))
    collector = Collector(store, "leynos", executable=str(executable), github=False)
    task = asyncio.create_task(collector.run(initial))
    try:
        async with asyncio.timeout(10):
            while True:
                current = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
                if current.collector.state == "following":
                    break
                await asyncio.sleep(0.01)
        assert current.sessions[0].repo_full_name == "leynos/fixture", (
            "Catalogue enrichment must retain the repository association."
        )
        assert current.sessions[0].stage == "planning", (
            "A successful empty PR association must classify as Planning."
        )
        assert current.sessions[0].state == "unknown", (
            "Metadata alone must not invent running activity."
        )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        final = msgspec.convert(await store.snapshot(), type=SnapshotStatus)
        assert final.collector.state == "stopped", (
            "Cancellation must persist stopped health after reaping the child."
        )
        await store.close()
