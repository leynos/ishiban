"""Test the on-demand agent detail reader through fake Lody executables."""

import asyncio
import typing as typ

import msgspec
import pytest

from ishiban import session_agent, session_show
from ishiban.session_agent import AgentDetails
from tests.lody_process_support import create_fake_lody, wait_for_calls

if typ.TYPE_CHECKING:
    import pathlib

    from tests.lody_reader_fixtures import SessionAgentResponseOptions


def _session_response(
    **options: typ.Unpack[SessionAgentResponseOptions],
) -> dict[str, object]:
    """Build a metadata response with distinct Lody and ACP session IDs.

    Returns
    -------
    dict of str to object
        A root response containing bounded session agent metadata.
    """
    session_id = options.get("session_id", "@SESSION_ID@")
    workspace_id = options.get("workspace_id", "workspace-1")
    ok = options.get("ok", True)
    agent_type = options.get("agent_type", "claude-code")
    config_id = options.get("config_id", "config-1")
    return {
        "ok": ok,
        "workspace": {"id": workspace_id, "name": "workspace label"},
        "session": {
            "id": session_id,
            "acpSessionId": "acp-session-must-not-be-copied",
            "agentType": agent_type,
            "agentConfigId": config_id,
            "conversation": "must not be retained",
        },
    }


def _config_response(
    *,
    config_id: str = "@CONFIG_ID@",
    workspace_id: str = "workspace-1",
    ok: bool = True,
    name: str = "Reviewer configuration",
) -> dict[str, object]:
    """Build a configuration response that includes fields the reader must ignore.

    Returns
    -------
    dict of str to object
        A root response with the requested identity and display name.
    """
    return {
        "ok": ok,
        "workspaceId": workspace_id,
        "agentConfig": {
            "id": config_id,
            "name": name,
            "environment": {"TOKEN": "must not be retained"},
            "instructions": "must not be retained",
        },
    }


def _fake_lody(
    tmp_path: pathlib.Path,
    session_response: dict[str, object] | str,
    config_response: dict[str, object] | str | None = None,
    *,
    linger_after_output: float = 0,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Create a fake executable that emits separate session and config responses.

    Returns
    -------
    tuple of pathlib.Path
        The executable path followed by the command invocation log path.
    """
    session_payload = _json_payload(session_response)
    config_payload = _json_payload(
        config_response if config_response is not None else "not-json"
    )
    response_code = (
        "if args[:2] == ['session', 'show']:\n"
        f"    payload = {session_payload!r}\n"
        "else:\n"
        f"    payload = {config_payload!r}\n"
        "payload = payload.replace('@SESSION_ID@', args[2])\n"
        "payload = payload.replace('@CONFIG_ID@', args[2])\n"
    )
    return create_fake_lody(
        tmp_path,
        response_code,
        linger_after_output=linger_after_output,
    )


def _json_payload(response: dict[str, object] | str) -> str:
    """Encode one test response while allowing deliberately malformed output.

    Returns
    -------
    str
        JSON text or the supplied malformed text.
    """
    if isinstance(response, str):
        return response
    return msgspec.json.encode(response).decode("utf-8")


@pytest.mark.asyncio
async def test_read_validates_lody_ids_and_returns_only_agent_labels(
    tmp_path: pathlib.Path,
) -> None:
    """Metadata uses the Lody ID and two exact, secret-free CLI commands."""
    executable, call_log = _fake_lody(
        tmp_path,
        _session_response(),
        _config_response(),
        linger_after_output=120,
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1",
        "leynos",
        str(executable),
    )
    details = await asyncio.wait_for(service.read("lody-session-1"), timeout=3)
    assert details is not None, (
        "A valid session and config response must produce details."
    )
    assert details == AgentDetails(
        agent_type="claude-code",
        configuration_id="config-1",
        configuration_name="Reviewer configuration",
    ), "The result must contain only agent type and configuration ID and name."
    assert not hasattr(details, "session_id"), (
        "ACP and Lody session identities must not be copied into agent details."
    )
    assert await wait_for_calls(call_log, 2) == [
        "session\tshow\tlody-session-1\t--workspace\tleynos\t--json",
        "agent-config\tshow\tconfig-1\t--workspace\tleynos\t--json",
    ], "The reader must use read-only commands without secret-inclusion flags."


@pytest.mark.parametrize(
    ("response", "session_id", "case"),
    [
        (_session_response(workspace_id="other"), "lody-session-1", "workspace"),
        (_session_response(session_id="other"), "lody-session-1", "session ID"),
        (_session_response(ok=False), "lody-session-1", "ok flag"),
        ("not-json", "lody-session-1", "malformed JSON"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.asyncio
async def test_invalid_session_metadata_returns_none(
    tmp_path: pathlib.Path,
    response: dict[str, object] | str,
    session_id: str,
    case: str,
) -> None:
    """Unverified session metadata never becomes agent details."""
    executable, _call_log = _fake_lody(tmp_path, response)
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    assert await service.read(session_id) is None, (
        f"A session response with an invalid {case} must fail closed."
    )


@pytest.mark.asyncio
async def test_missing_config_id_is_valid_and_does_not_query_config(
    tmp_path: pathlib.Path,
) -> None:
    """A missing configuration ID yields labels without a second CLI call."""
    executable, call_log = _fake_lody(
        tmp_path,
        _session_response(config_id=None),
        _config_response(),
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    first = await service.read("lody-session-1")
    assert first == AgentDetails(agent_type="claude-code"), (
        "A session without configuration metadata is a valid partial result."
    )
    assert await service.read("lody-session-1") is first, (
        "A valid no-configuration result must use the successful cache."
    )
    assert await wait_for_calls(call_log) == [
        "session\tshow\tlody-session-1\t--workspace\tleynos\t--json"
    ], "A missing configuration ID must not trigger agent-config show."


@pytest.mark.asyncio
async def test_partial_config_failure_uses_short_cache_then_retries(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed config lookup preserves IDs briefly and can refresh later."""
    clock = [100.0]
    monkeypatch.setattr(session_agent, "_monotonic_time", lambda: clock[0])
    executable, call_log = _fake_lody(
        tmp_path,
        _session_response(),
        "not-json",
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    details = await service.read("lody-session-1")
    assert details == AgentDetails(
        agent_type="claude-code",
        configuration_id="config-1",
        configuration_name=None,
    ), "A config failure must retain verified session metadata."
    assert await service.read("lody-session-1") is details, (
        "A partial result must be reused during its short failure cache."
    )
    assert len(await wait_for_calls(call_log, 2)) == 2, (
        "A partial cache hit must not repeat either CLI command."
    )
    clock[0] += session_agent.FAILURE_CACHE_SECONDS + 1
    assert await service.read("lody-session-1") is not None, (
        "Retrying after partial expiry must still return verified session metadata."
    )
    assert len(await wait_for_calls(call_log, 3)) == 3, (
        "Retrying a failed config lookup must reuse the verified session show."
    )


@pytest.mark.parametrize(
    ("response", "case"),
    [
        (_config_response(workspace_id="other"), "workspace"),
        (_config_response(config_id="other"), "configuration ID"),
        (_config_response(ok=False), "ok flag"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.asyncio
async def test_unverified_config_returns_partial_session_details(
    tmp_path: pathlib.Path,
    response: dict[str, object],
    case: str,
) -> None:
    """Unverified config metadata cannot replace a verified session config ID."""
    executable, _call_log = _fake_lody(tmp_path, _session_response(), response)
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    details = await service.read("lody-session-1")
    assert details == AgentDetails(
        agent_type="claude-code",
        configuration_id="config-1",
        configuration_name=None,
    ), f"A config response with an invalid {case} must leave its name unavailable."


@pytest.mark.asyncio
async def test_cache_is_keyed_by_session_and_expires_successfully(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful metadata is cached for five minutes and then refreshed."""
    clock = [10.0]
    monkeypatch.setattr(session_agent, "_monotonic_time", lambda: clock[0])
    monkeypatch.setattr(session_show, "_monotonic_time", lambda: clock[0])
    executable, call_log = _fake_lody(
        tmp_path,
        _session_response(),
        _config_response(),
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    first, concurrent = await asyncio.gather(
        service.read("lody-session-1"),
        service.read("lody-session-1"),
    )
    assert first is not None, "Valid session and config metadata must be returned."
    assert concurrent is first, (
        "Concurrent reads must share one serialized session/config pipeline."
    )
    clock[0] += session_agent.SUCCESS_CACHE_SECONDS + 1
    assert await service.read("lody-session-1") is not None, (
        "A successful cache entry must refresh after five minutes."
    )
    assert len(await wait_for_calls(call_log, 4)) == 4, (
        "Only the first read and the post-expiry read should run command pairs."
    )


@pytest.mark.asyncio
async def test_long_config_id_is_omitted_instead_of_truncated(
    tmp_path: pathlib.Path,
) -> None:
    """An overlong configuration identity is omitted and never queried."""
    long_id = "x" * (session_agent.MAX_CONFIGURATION_ID_LENGTH + 1)
    executable, call_log = _fake_lody(
        tmp_path,
        _session_response(config_id=long_id),
        _config_response(),
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    details = await service.read("lody-session-1")
    assert details == AgentDetails(agent_type="claude-code"), (
        "An invalid long configuration ID must not be truncated or exposed."
    )
    assert len(await wait_for_calls(call_log)) == 1, (
        "An invalid configuration ID must not be passed to another CLI command."
    )


@pytest.mark.asyncio
async def test_configuration_name_is_bounded_for_display(
    tmp_path: pathlib.Path,
) -> None:
    """Long configuration names are bounded without truncating IDs."""
    name = "n" * (session_agent.MAX_CONFIGURATION_NAME_LENGTH + 50)
    executable, _call_log = _fake_lody(
        tmp_path,
        _session_response(),
        _config_response(name=name),
    )
    service = session_agent.SessionAgentDetails(
        "workspace-1", "leynos", str(executable)
    )
    details = await service.read("lody-session-1")
    assert details is not None, "A valid long display name must remain usable."
    assert details.configuration_id == "config-1", (
        "The configuration identity must remain exact."
    )
    assert details.configuration_name == name[:512], (
        "Only the display name may be truncated to its configured bound."
    )
