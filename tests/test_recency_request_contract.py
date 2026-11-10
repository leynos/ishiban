"""Exercise the actual browser request against Falcon's strict batch decoder."""

import asyncio
import json
import os
import pathlib
import typing as typ

import pytest
from batch_activity_support import seed_unknown_sessions
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


async def _capture_browser_request(directory: pathlib.Path) -> bytes:
    """Run the real recency hook and retain its wire body for Falcon.

    For example, an extra browser field is rejected by the server in the
    integration test rather than accepted by a permissive fetch mock.

    Returns
    -------
    bytes
        The browser controller's actual JSON request body.
    """
    capture = directory / "recency-request.json"
    environment = {**os.environ, "ISHIBAN_RECENCY_REQUEST_CAPTURE": str(capture)}
    process = await asyncio.create_subprocess_exec(
        "bun",
        "test",
        "tests/recency-request-contract.test.tsx",
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        async with asyncio.timeout(20):
            output, _ = await process.communicate()
        assert process.returncode == 0, output.decode(errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return await asyncio.to_thread(capture.read_bytes)


def _show_member(invocation: Invocation) -> Response:
    """Supply a verified history-free member without any Lody mutation.

    Returns
    -------
    Response
        The minimal source metadata envelope for the requested member.
    """
    assert invocation.args[:2] == ["session", "show"], (
        "The recency contract must use read-only session show."
    )
    return Response(
        stdout=json.dumps({
            "ok": True,
            "workspace": {"id": "w1"},
            "session": {"id": invocation.args[2]},
            "latestHistoryAt": None,
        })
    )


@pytest.mark.asyncio
async def test_browser_recency_payload_passes_real_asgi_decoder(
    tmp_path: pathlib.Path,
    cmd_mox: CmdMox,
) -> None:
    """A browser-generated batch must reach the real metadata resolver."""
    body = await _capture_browser_request(tmp_path)
    lody = cmd_mox.spy("lody").runs(_show_member)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["child-0", "root-0"])
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            result = await conductor.simulate_post(
                "/api/v1/sessions/recency",
                body=body,
                headers={"content-type": "application/json"},
            )
            after = (await store.snapshot(), await store.events(0))

    assert result.status_code == 200, (
        f"The actual browser body must pass the strict ASGI decoder: {result.text}"
    )
    frames = [json.loads(line) for line in result.content.splitlines()]
    assert len(frames) == 2, "Each requested member must produce exactly one result."
    assert {frame["sessionId"] for frame in frames} == {"root-0", "child-0"}, (
        "Both browser-requested identities must reach the response."
    )
    assert all(frame["outcome"] == "available" for frame in frames), (
        "The request must reach the mocked CLI, not merely return HTTP 200."
    )
    assert len(lody.invocations) == 2, "Each uncached member must be resolved once."
    assert before == after, "Contract validation must leave the journal unchanged."
