"""Exercise byte bounds and child cleanup in the cross-runtime Bun fixture."""

import asyncio
import typing as typ

import pytest
from bun_test_capture import MAX_CAPTURE_BYTES, capture_bun_test_output

if typ.TYPE_CHECKING:
    from pathlib import Path


class LimitScenario(typ.NamedTuple):
    """One real Bun writer and the limit outcome it must prove."""

    name: str
    source: str
    diagnostic: str
    should_kill: bool


@pytest.fixture
def spawned_children(
    monkeypatch: pytest.MonkeyPatch,
) -> list[asyncio.subprocess.Process]:
    """Track real Bun children so limit failures prove the child was reaped.

    Returns
    -------
    list[asyncio.subprocess.Process]
        The actual processes created by the capture helper.
    """
    children: list[asyncio.subprocess.Process] = []
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
        child = await start(*command, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", track)
    return children


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
                should_kill=True,
            ),
            id="stdout-flood-kills-child",
        ),
        pytest.param(
            LimitScenario(
                name="capture-file",
                source=(
                    "import {test} from 'bun:test';\n"
                    "test('capture', async () => {\n"
                    "  const path = Bun.env.ISHIBAN_TEST_CAPTURE;\n"
                    "  if (!path) throw new Error('Missing capture path');\n"
                    "  await Bun.write(path, "
                    f"new Uint8Array({MAX_CAPTURE_BYTES + 1}));\n"
                    "});\n"
                ),
                diagnostic="capture > 1 MiB",
                should_kill=False,
            ),
            id="capture-file-rejects-successful-child",
        ),
    ],
)
@pytest.mark.asyncio
async def test_real_bun_capture_limits_reap_their_child(
    tmp_path: Path,
    spawned_children: list[asyncio.subprocess.Process],
    scenario: LimitScenario,
) -> None:
    """Bound each real Bun output channel and verify its distinct exit path."""
    test_file = tmp_path / f"{scenario.name}.test.ts"
    test_file.write_text(scenario.source)

    with pytest.raises(AssertionError, match=scenario.diagnostic):
        await capture_bun_test_output(
            tmp_path, test_file=str(test_file), variable="ISHIBAN_TEST_CAPTURE"
        )

    assert len(spawned_children) == 1, "The limit must exercise one real Bun child."
    returncode = spawned_children[0].returncode
    assert returncode is not None, "The limit path must reap its Bun child."
    if scenario.should_kill:
        assert returncode < 0, "Stdout overflow must kill the still-running child."
    else:
        assert returncode == 0, "Capture overflow must reject a successful child."
