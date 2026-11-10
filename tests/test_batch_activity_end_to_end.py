"""Exercise batch activity through Falcon and actual isolated CLI processes."""

import json
import typing as typ

import pytest
from batch_activity_support import remember_idle_activity, seed_unknown_sessions
from cmd_mox import Invocation, Response
from falcon import testing
from storage_support import opened_store

from ishiban.api import create_app
from ishiban.domain import CatalogueEntry

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


def _observe(invocation: Invocation) -> Response:
    """Produce independently successful and unavailable command responses.

    Returns
    -------
    Response
        A complete JSON object written by the real CmdMox shim process.

    Raises
    ------
    AssertionError
        If the API requests an unexpected command or session.
    """
    match invocation.args:
        case ["session", "observe", session_id, "--workspace", "w1", "--json"] if (
            session_id in {"s2", "s3"}
        ):
            return Response(
                stdout=json.dumps({
                    "ok": session_id == "s2",
                    "version": 1,
                    "workspaceId": "w1",
                    "session": {
                        "sessionId": session_id,
                        "state": "running" if session_id == "s2" else "unknown",
                        "source": "persisted" if session_id == "s2" else "metadata",
                        "freshness": "synced",
                    },
                })
            )
        case _:
            message = "Only uncached unknown session observations are allowed."
            raise AssertionError(message)


@pytest.mark.asyncio
async def test_batch_api_reads_mocked_lody_and_keeps_journal_unchanged(
    tmp_path: Path, cmd_mox: CmdMox
) -> None:
    """Cached, successful and unavailable members use separate batch outcomes."""
    lody = cmd_mox.spy("lody").runs(_observe)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["s1", "s2", "s3"])
        await remember_idle_activity(store, "s1")
        journal_before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            response = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({
                    "sessionIds": ["s1", "s2", "s3", "missing"],
                }),
                headers={"content-type": "application/json"},
            )
            journal_after = (await store.snapshot(), await store.events(0))

    by_session = {
        frame["sessionId"]: frame
        for line in response.content.splitlines()
        for frame in [json.loads(line)]
    }
    assert response.status_code == 200, "The ASGI batch route must succeed."
    assert set(by_session) == {"s1", "s2", "s3", "missing"}, (
        "The batch emits one frame for each unique requested identity."
    )
    assert by_session["s1"]["session"]["activitySource"] == "lazy", (
        "The cache hit must be returned without a CLI process."
    )
    assert by_session["s2"]["session"]["state"] == "running", (
        "The fake CLI's valid persisted response must resolve s2."
    )
    assert by_session["s2"]["session"]["activitySource"] == "lazy", (
        "Fresh CLI activity must be labelled in the response."
    )
    assert by_session["s3"]["session"] is None, (
        "The unsuccessful s3 response must not abort other batch members."
    )
    assert by_session["missing"]["session"] is None, (
        "A missing identity must produce a null frame without a CLI call."
    )
    assert len(lody.invocations) == 2, "Exactly two uncached sessions must be read."
    assert {invocation.args[2] for invocation in lody.invocations} == {"s2", "s3"}, (
        "Only uncached unknown sessions should start Lody processes."
    )
    assert journal_after[0] == journal_before[0], (
        "Lazy results must not rewrite the journal."
    )
    assert journal_after[1] == journal_before[1], "Lazy results must not append events."


@pytest.mark.asyncio
async def test_large_cached_member_yields_marker_before_small_sibling(
    tmp_path: Path, cmd_mox: CmdMox
) -> None:
    """A large accepted observation cannot abort a later batch member."""

    def observe(invocation: Invocation) -> Response:
        """Supply one near-limit read and one small successful sibling.

        Returns
        -------
        Response
            Read-only Lody JSON for the requested fixture session.

        Raises
        ------
        AssertionError
            If the API asks for an unexpected command.
        """
        match invocation.args:
            case ["session", "observe", "large", "--workspace", "w1", "--json"]:
                turns = [
                    {"userTurnId": f"u{index:03}{'x' * 9900}", "state": "pending"}
                    for index in range(100)
                ]
                session = {
                    "sessionId": "large",
                    "state": "waiting",
                    "source": "persisted",
                    "freshness": "synced",
                    "activeTurns": turns,
                }
            case ["session", "observe", "small", "--workspace", "w1", "--json"]:
                session = {
                    "sessionId": "small",
                    "state": "running",
                    "source": "persisted",
                    "freshness": "synced",
                }
            case _:
                message = "Only the large and small fixture reads are expected."
                raise AssertionError(message)
        return Response(
            stdout=json.dumps({
                "ok": True,
                "version": 1,
                "workspaceId": "w1",
                "session": session,
            })
        )

    lody = cmd_mox.spy("lody").runs(observe)
    async with opened_store(tmp_path) as store:
        await seed_unknown_sessions(store, ["large", "small"])
        generation = await store.begin_generation()
        await store.catalogue(
            CatalogueEntry(
                session_id="large",
                machine_id="machine-1",
                title="t" * 100_000,
                archived=False,
                repo_full_name=None,
                branch_name=None,
                pull_requests=[],
                stage="planning",
                stage_reason="No associated PR.",
            ),
            generation,
        )
        journal_before = (await store.snapshot(), await store.events(0))
        async with testing.ASGIConductor(create_app(store)) as conductor:
            first = await conductor.simulate_get("/api/v1/sessions/large/activity")
            batch = await conductor.simulate_post(
                "/api/v1/sessions/activity",
                body=json.dumps({"sessionIds": ["large", "small"]}),
                headers={"content-type": "application/json"},
            )
            fallback = await conductor.simulate_get(
                "/api/v1/sessions/large/activity?includeKnown=true"
            )
            journal_after = (await store.snapshot(), await store.events(0))
            private = await store.session_projection("large")
            assert private is not None, "The large session must remain materialized."
            restored = (await store.restore_activity([private]))[0]

    frames = [json.loads(line) for line in batch.content.splitlines(keepends=True)]
    assert first.status_code == 200, "The large observation must be accepted."
    assert first.json["session"] is not None, (
        f"A near-limit Lody observation must resolve; calls={len(lody.invocations)}."
    )
    assert len(json.dumps(first.json).encode()) > 1_048_576, (
        "The public single-session result must exceed one batch frame."
    )
    assert len(frames) == 2, "Every requested member needs one batch outcome."
    assert all(
        len(line) <= 1_048_576 for line in batch.content.splitlines(keepends=True)
    ), "Every emitted NDJSON frame must fit the browser's frame limit."
    assert frames[0] == {
        "workspaceId": "w1",
        "sessionId": "large",
        "outcome": "response_too_large",
    }, "The cached large member must yield an explicit bounded marker first."
    assert frames[1]["session"]["state"] == "running", (
        "A later small sibling must still resolve after the oversized member."
    )
    assert fallback.json["session"]["title"] == "t" * 100_000, (
        "The fallback read must retain the complete accepted title."
    )
    assert len(typ.cast("list[object]", restored["activeTurns"])) == 100, (
        "The cached private observation must retain every accepted turn."
    )
    assert len(lody.invocations) == 2, (
        "The fallback must reuse cache instead of invoking Lody again."
    )
    assert journal_after == journal_before, (
        "On-demand reads must leave the source journal untouched."
    )
