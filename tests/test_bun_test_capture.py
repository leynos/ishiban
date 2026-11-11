"""Exercise byte bounds and child cleanup in the cross-runtime Bun fixture."""

import asyncio
import fcntl
import json
import os
import time
import typing as typ
from pathlib import Path

import pytest
from bun_test_capture import MAX_CAPTURE_BYTES, capture_bun_test_output

WRITER_PATH = Path(__file__).resolve().parent / "capture-writer.ts"
WRITER_IMPORT = (
    "import {writeCapturedText} from " + json.dumps(str(WRITER_PATH)) + ";\n"
)
CAPTURE_SCRIPT_PREFIX = "import {test} from 'bun:test';\n" + WRITER_IMPORT


class LimitScenario(typ.NamedTuple):
    """One real Bun writer and the limit outcome it must prove."""

    name: str
    source: str
    diagnostic: str


class TrackedChildren(typ.NamedTuple):
    """Real child processes and a signal that the first one was spawned."""

    processes: list[asyncio.subprocess.Process]
    started: asyncio.Event


def _force_small_fifo(path: Path) -> int:
    """Set one real FIFO to 4 KiB to expose partial-write behaviour.

    Returns
    -------
    int
        The effective Linux pipe capacity in bytes.
    """
    if not hasattr(fcntl, "F_SETPIPE_SZ"):
        pytest.skip("The 4 KiB FIFO regression requires Linux F_SETPIPE_SZ.")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        return fcntl.fcntl(fd, fcntl.F_SETPIPE_SZ, 4096)
    finally:
        os.close(fd)


@pytest.fixture
def spawned_children(
    monkeypatch: pytest.MonkeyPatch,
) -> TrackedChildren:
    """Track real Bun children so limit failures prove the child was reaped.

    Returns
    -------
    TrackedChildren
        The actual processes and their first-spawn signal.
    """
    children: list[asyncio.subprocess.Process] = []
    started = asyncio.Event()
    start = asyncio.create_subprocess_exec

    async def track(
        *command: str,
        cwd: Path,
        env: dict[str, str],
        stdout: int,
        stderr: int,
    ) -> asyncio.subprocess.Process:
        """Record the real process without changing its transport behaviour.

        Returns
        -------
        asyncio.subprocess.Process
            The child created by the original asyncio subprocess API.
        """
        is_fifo = await asyncio.to_thread(Path(env["ISHIBAN_TEST_CAPTURE"]).is_fifo)
        assert is_fifo, (
            "The child must write to a bounded FIFO, never a growing regular file."
        )
        capacity = await asyncio.to_thread(
            _force_small_fifo, Path(env["ISHIBAN_TEST_CAPTURE"])
        )
        assert capacity == 4096, "The regression needs a 4 KiB FIFO."
        child = await start(*command, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
        children.append(child)
        started.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", track)
    return TrackedChildren(children, started)


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            LimitScenario(
                name="stdout-flood",
                source=(
                    "import {test} from 'bun:test';\n"
                    "import {writeSync} from 'node:fs';\n"
                    "test('flood', async () => {\n"
                    f"  writeSync(1, 'x'.repeat({MAX_CAPTURE_BYTES + 1}));\n"
                    "  await new Promise(() => {});\n"
                    "});\n"
                ),
                diagnostic="stdout > 1 MiB",
            ),
            id="stdout-flood-kills-child",
        ),
        pytest.param(
            LimitScenario(
                name="capture-fifo",
                source=CAPTURE_SCRIPT_PREFIX
                + (
                    "test('capture', async () => {\n"
                    "  const path = Bun.env.ISHIBAN_TEST_CAPTURE;\n"
                    "  if (!path) throw new Error('Missing capture path');\n"
                    f"  writeCapturedText(path, 'x'.repeat({MAX_CAPTURE_BYTES * 2}));\n"
                    "  await new Promise(() => {});\n"
                    "});\n"
                ),
                diagnostic="capture > 1 MiB",
            ),
            id="capture-overflow-kills-child",
        ),
    ],
)
@pytest.mark.asyncio
async def test_real_bun_capture_limits_reap_their_child(
    tmp_path: Path,
    spawned_children: TrackedChildren,
    scenario: LimitScenario,
) -> None:
    """Bound each real Bun output channel and verify its distinct exit path."""
    test_file = tmp_path / f"{scenario.name}.test.ts"
    test_file.write_text(scenario.source)

    started = time.monotonic()
    with pytest.raises(AssertionError, match=scenario.diagnostic):
        await capture_bun_test_output(
            tmp_path, test_file=str(test_file), variable="ISHIBAN_TEST_CAPTURE"
        )

    assert time.monotonic() - started < 5, (
        "A channel overflow must fail before the 20-second deadline."
    )
    assert len(spawned_children.processes) == 1, (
        "The limit must exercise one real Bun child."
    )
    assert not (tmp_path / "ishiban_test_capture.json").exists(), (
        "The private FIFO must be removed after a failed run."
    )
    returncode = spawned_children.processes[0].returncode
    assert returncode is not None, "The limit path must reap its Bun child."
    assert returncode < 0, "Channel overflow must kill the still-running child."


@pytest.mark.parametrize("size", [0, MAX_CAPTURE_BYTES], ids=["empty", "at-limit"])
@pytest.mark.asyncio
async def test_fifo_preserves_valid_capture_boundaries(
    tmp_path: Path,
    spawned_children: TrackedChildren,
    size: int,
) -> None:
    """An empty or exactly one MiB FIFO payload remains byte-for-byte valid."""
    test_file = tmp_path / "valid-capture.test.ts"
    test_file.write_text(
        CAPTURE_SCRIPT_PREFIX
        + (
            "test('capture', async () => {\n"
            "  const path = Bun.env.ISHIBAN_TEST_CAPTURE;\n"
            "  if (!path) throw new Error('Missing capture path');\n"
            f"  writeCapturedText(path, 'x'.repeat({size}));\n"
            "});\n"
        )
    )

    content = await capture_bun_test_output(
        tmp_path, test_file=str(test_file), variable="ISHIBAN_TEST_CAPTURE"
    )

    assert content == b"x" * size, "The FIFO must preserve all valid capture bytes."
    assert len(spawned_children.processes) == 1, (
        "The boundary must use one real Bun child."
    )
    assert spawned_children.processes[0].returncode == 0, (
        "The valid child must exit normally."
    )
    assert not (tmp_path / "ishiban_test_capture.json").exists(), (
        "The private FIFO must be removed after a successful run."
    )


@pytest.mark.asyncio
async def test_multibyte_capture_preserves_exact_bytes_across_small_fifo(
    tmp_path: Path, spawned_children: TrackedChildren
) -> None:
    """A 4 KiB FIFO must not duplicate a patterned multibyte JSON payload."""
    payload = json.dumps(
        {"values": [f"{index:04x}🙂" for index in range(1200)]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    expected = payload.encode()
    assert len(expected) > 8192, "The regression must cross a partial write."
    test_file = tmp_path / "patterned-capture.test.ts"
    test_file.write_text(
        CAPTURE_SCRIPT_PREFIX
        + (
            "test('capture', async () => {\n"
            "  const path = Bun.env.ISHIBAN_TEST_CAPTURE;\n"
            "  if (!path) throw new Error('Missing capture path');\n"
            f"  writeCapturedText(path, {json.dumps(payload, ensure_ascii=False)});\n"
            "});\n"
        )
    )

    captured = await capture_bun_test_output(
        tmp_path, test_file=str(test_file), variable="ISHIBAN_TEST_CAPTURE"
    )

    assert captured == expected, "The FIFO must preserve every UTF-8 byte once."
    assert spawned_children.processes[0].returncode == 0, (
        "The writer must exit successfully after a complete capture."
    )


@pytest.mark.asyncio
async def test_cancellation_reaps_bun_child_and_removes_fifo(
    tmp_path: Path, spawned_children: TrackedChildren
) -> None:
    """A cancelled capture leaves neither a running child nor a private FIFO."""
    test_file = tmp_path / "cancelled-capture.test.ts"
    test_file.write_text(
        "import {test} from 'bun:test';\n"
        "test('wait', async () => { await new Promise(() => {}); });\n"
    )
    task = asyncio.create_task(
        capture_bun_test_output(
            tmp_path, test_file=str(test_file), variable="ISHIBAN_TEST_CAPTURE"
        )
    )
    await asyncio.wait_for(spawned_children.started.wait(), timeout=2)
    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    returncode = spawned_children.processes[0].returncode
    assert returncode is not None, "Cancellation must reap the real Bun child."
    assert returncode < 0, "Cancellation must stop the waiting child."
    assert not (tmp_path / "ishiban_test_capture.json").exists(), (
        "Cancellation must remove the private FIFO."
    )
