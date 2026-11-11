"""Verify a built wheel can migrate and collect outside the checkout."""

import contextlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess  # ruff: ignore[suspicious-subprocess-import] - exercise the real wheel in an isolated interpreter.
import sys
import time
import zipfile
from pathlib import Path

from lody_process_support import create_fake_lody


def _install_fake_lody(directory: Path) -> Path:
    """Install a bounded fake; for example, list and observe use fixture facts.

    Returns
    -------
    Path
        The fake executable's command log.
    """
    fixtures = Path(__file__).parent / "fixtures"
    catalogue = (fixtures / "lody-catalogue.json").read_text(encoding="utf-8")
    events = (fixtures / "lody-observer.jsonl").read_text(encoding="utf-8")
    events += (fixtures / "lody-observer-activity.jsonl").read_text(encoding="utf-8")
    fake_lody, calls = create_fake_lody(
        directory,
        f"payload = {catalogue!r} if 'list' in args else {events!r}",
        linger_after_output=120,
    )
    fake_lody.rename(directory / "lody")
    return calls


def _wait_for_observer_row(database: Path, process: subprocess.Popen[str]) -> None:
    """Wait for one row; for example, fail if the collector exits first.

    Raises
    ------
    AssertionError
        When the bounded wait expires before observing the event.
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if database.exists():
            with (
                contextlib.suppress(sqlite3.OperationalError),
                sqlite3.connect(database) as connection,
            ):
                row = connection.execute(
                    "SELECT count(*) FROM source_events "
                    "WHERE source = 'lody.observe' "
                    "AND event_type = 'session.changed'"
                ).fetchone()
                if row is not None and row[0] == 1:
                    return
        if process.poll() is not None:
            break
        time.sleep(0.05)
    message = "The installed collector must persist the fake observer event."
    raise AssertionError(message)


def _assert_collector_journal(database: Path, calls: Path) -> None:
    """Read durable results; for example, a running event survives CLI shutdown."""
    with sqlite3.connect(database) as connection:
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        journal = connection.execute(
            "SELECT session_id, projection_json FROM source_events "
            "WHERE source = 'lody.observe' AND event_type = 'session.changed'"
        ).fetchone()
        health = connection.execute("SELECT state FROM collector_state").fetchone()
    assert head == ("0001_initial_journal",), (
        "The installed collector must migrate before ingestion."
    )
    assert journal is not None, "The installed collector must retain its event."
    assert journal[0] == "session", "The fixture session ID must survive ingestion."
    assert json.loads(journal[1])["state"] == "running", (
        "The observer event must persist its running projection."
    )
    assert health == ("stopped",), "SIGINT must stop the collector cleanly."
    invocation_log = calls.read_text(encoding="utf-8")
    assert "session\tlist" in invocation_log, "The fake must serve the catalogue."
    assert "session\tobserve" in invocation_log, "The fake must serve observation."


def _collect_from_wheel(installed: Path, directory: Path) -> None:
    """Run the installed CLI; for example, retain one fake observer event."""
    bin_directory = directory / "bin"
    calls = _install_fake_lody(bin_directory)
    state = directory / "collector-state"
    launcher = """
import sys
from pathlib import Path
installed = Path(sys.argv.pop(1))
sys.path.insert(0, str(installed))
import ishiban
assert Path(ishiban.__file__).is_relative_to(installed)
from ishiban.cli import app
app()
"""
    environment = {
        "PATH": f"{bin_directory}{os.pathsep}{os.defpath}",
        "PYTHONUNBUFFERED": "1",
    }
    database = state / "observatory.sqlite3"
    with subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] - isolated interpreter and fixture PATH, no shell.
        [
            sys.executable,
            "-I",
            "-c",
            launcher,
            str(installed),
            "collect",
            "--workspace",
            "leynos",
            "--state-directory",
            str(state),
            "--no-github",
        ],
        cwd=directory,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            _wait_for_observer_row(database, process)
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
            assert process.returncode in {0, 130}, (
                f"Collector did not stop cleanly: {stderr[-2000:]}"
            )
            assert "Workspace catalogue connected" in stdout, (
                "The installed CLI must reach its collector command path."
            )
        finally:
            # Reap the private process group if an assertion interrupted shutdown.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
    _assert_collector_journal(database, calls)


def test_wheel_initializes_schema_from_packaged_migrations(tmp_path: Path) -> None:
    """An extracted wheel migrates and collects without repository files."""
    repository = Path(__file__).parents[1]
    uv = shutil.which("uv")
    assert uv is not None, "Wheel integration needs the repository's uv tool."
    wheels = tmp_path / "wheels"
    build = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed uv arguments, no shell.
        [uv, "build", "--wheel", "--out-dir", str(wheels)],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert build.returncode == 0, f"The wheel must build: {build.stderr[-2000:]}"
    built_wheels = list(wheels.glob("ishiban-*.whl"))
    assert len(built_wheels) == 1, "Build exactly one Ishiban wheel for this test."
    installed = tmp_path / "installed"
    with zipfile.ZipFile(built_wheels[0]) as wheel:
        wheel.extractall(installed)

    probe = """
import asyncio
import sqlite3
import sys
from pathlib import Path

installed = Path(sys.argv[1])
database = Path(sys.argv[2])
sys.path.insert(0, str(installed))
import ishiban
from ishiban.storage import Store

assert Path(ishiban.__file__).is_relative_to(installed)

async def initialize():
    store = Store(f"sqlite+aiosqlite:///{database}", "wheel-probe")
    try:
        await store.initialize()
        snapshot = await store.snapshot()
        assert snapshot["workspaceId"] == "wheel-probe"
        assert snapshot["cursor"] == 0
    finally:
        await store.close()

asyncio.run(initialize())
with sqlite3.connect(database) as connection:
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == ("0001_initial_journal",)
print("wheel migration passed")
"""
    run = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - isolated interpreter and fixed probe, no shell.
        [
            sys.executable,
            "-I",
            "-c",
            probe,
            str(installed),
            str(tmp_path / "wheel.sqlite3"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert run.returncode == 0, f"Installed wheel must migrate: {run.stderr[-2000:]}"
    assert run.stdout.strip() == "wheel migration passed", (
        "The isolated wheel must reach the migrated snapshot."
    )
    _collect_from_wheel(installed, tmp_path)
