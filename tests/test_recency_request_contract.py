"""Exercise the actual browser request against Falcon's strict batch decoder."""

import json
import typing as typ

import pytest
from batch_activity_support import seed_unknown_sessions
from bun_test_capture import capture_bun_test_output
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox


async def _capture_browser_request(
    directory: pathlib.Path,
    *,
    variable: str = "ISHIBAN_RECENCY_REQUEST_CAPTURE",
) -> bytes:
    """Run the real recency hook and retain its wire body for Falcon.

    For example, an extra browser field is rejected by the server in the
    integration test rather than accepted by a permissive fetch mock.

    Returns
    -------
    bytes
        The browser controller's actual JSON request body.
    """
    return await capture_bun_test_output(
        directory,
        test_file="tests/recency-request-contract.test.tsx",
        variable=variable,
    )


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
            "session": {"id": invocation.args[-1]},
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


@pytest.mark.asyncio
async def test_multibyte_browser_batches_pass_real_asgi_decoder(
    tmp_path: pathlib.Path,
    cmd_mox: CmdMox,
) -> None:
    """Accepted long IDs reach Falcon in separate requests within its byte cap."""
    captured = await _capture_browser_request(
        tmp_path, variable="ISHIBAN_RECENCY_MULTIBYTE_CAPTURE"
    )
    bodies: list[str] = json.loads(captured)
    member_ids = [
        session_id for body in bodies for session_id in json.loads(body)["sessionIds"]
    ]
    assert len(bodies) == 2, "The browser must split this eight-member byte load."
    assert len(member_ids) == 8, "Splitting must deliver every accepted member."
    assert len(set(member_ids)) == 8, "Each accepted member must appear only once."
    assert all(len(session_id) == 256 for session_id in member_ids), (
        "The fixture must use Python's 256-code-point acceptance boundary."
    )
    assert all(len(body.encode()) <= 8192 for body in bodies), (
        "Every actual browser payload must respect Falcon's request limit."
    )

    lody = cmd_mox.spy("lody").runs(_show_member)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, member_ids)
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            results = [
                await conductor.simulate_post(
                    "/api/v1/sessions/recency",
                    body=body.encode(),
                    headers={"content-type": "application/json"},
                )
                for body in bodies
            ]
            after = (await store.snapshot(), await store.events(0))
    assert [result.status_code for result in results] == [200, 200], (
        "Both actual wire requests must pass Falcon's decoder."
    )
    frames = [
        json.loads(line) for result in results for line in result.content.splitlines()
    ]
    assert {frame["sessionId"] for frame in frames} == set(member_ids), (
        "The resolver must echo all requested identities without normalization."
    )
    assert all(frame["outcome"] == "available" for frame in frames), (
        "Each accepted ID must reach the bounded read-only CLI resolver."
    )
    assert len(lody.invocations) == 8, "The native adapter must read each ID once."
    assert before == after, "Recency enrichment must not mutate the journal."


@pytest.mark.asyncio
async def test_unsupported_source_id_does_not_reject_valid_browser_sibling(
    tmp_path: pathlib.Path,
    cmd_mox: CmdMox,
) -> None:
    """A 257-code-point catalogue tab stays off the wire while its root resolves."""
    body = await _capture_browser_request(
        tmp_path, variable="ISHIBAN_RECENCY_UNSUPPORTED_CAPTURE"
    )
    assert json.loads(body)["sessionIds"] == ["root-0"], (
        "The browser must isolate the valid sibling before Falcon sees the batch."
    )
    lody = cmd_mox.spy("lody").runs(_show_member)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["root-0", "x" * 257])
        before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            result = await conductor.simulate_post(
                "/api/v1/sessions/recency",
                body=body,
                headers={"content-type": "application/json"},
            )
            after = (await store.snapshot(), await store.events(0))
    assert result.status_code == 200, "The isolated valid request must pass Falcon."
    frames = [json.loads(line) for line in result.content.splitlines()]
    assert [frame["sessionId"] for frame in frames] == ["root-0"], (
        "The valid sibling must receive exactly one result."
    )
    assert frames[0]["outcome"] == "available", "The valid root must resolve."
    assert len(lody.invocations) == 1, "Only the requestable ID reaches Lody."
    assert before == after, "On-demand recency must leave the journal unchanged."
