"""Exercise PR enrichment lifecycle and subprocess failure boundaries."""

import json
import os
import sys
import typing as typ

import pytest

from ishiban.collector import Collector
from ishiban.domain import CatalogueEntry, PullRequest
from ishiban.lody import read_pull_requests
from ishiban.protocol import Catalogue, RawPR, RawSession

if typ.TYPE_CHECKING:
    import pathlib

    from ishiban.storage import Store

PR_URL = "https://github.com/example/project/pull/1"


class RecordingStore:
    """Capture catalogue writes made by the collector."""

    workspace_id = "workspace"

    def __init__(self) -> None:
        """Start without any catalogue writes recorded."""
        self.entries: list[CatalogueEntry] = []

    async def catalogue(self, entry: CatalogueEntry, generation: int) -> int | None:
        """Record an entry; for example, retain its terminal PR status.

        Returns
        -------
        int
            A stable sentinel cursor for the recorded entry.
        """
        self.entries.append(entry)
        return 1


def fake_gh(directory: pathlib.Path, source: str) -> pathlib.Path:
    """Install a temporary executable that supplies controlled GraphQL output.

    Returns
    -------
    pathlib.Path
        The executable path placed at the front of PATH by each test.
    """
    executable = directory / "gh"
    executable.write_text(source, encoding="utf-8")
    executable.chmod(0o700)
    return executable


def enable_fake_gh(monkeypatch: pytest.MonkeyPatch, directory: pathlib.Path) -> None:
    """Put one temporary executable ahead of the user's normal PATH."""
    current_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", os.pathsep.join([str(directory), current_path]))


def make_catalogue(urls: list[str], status: str = "open") -> Catalogue:
    """Create one bounded association per URL for collector reconciliation.

    Returns
    -------
    Catalogue
        A successful catalogue containing the supplied PR associations.
    """
    return Catalogue(
        ok=True,
        workspace_id="workspace",
        sessions=[
            RawSession(
                id=f"session-{index}",
                pull_requests=[RawPR(url=url, status=status)],
            )
            for index, url in enumerate(urls)
        ],
    )


def _collector_with_cached_pr(request: PullRequest) -> tuple[RecordingStore, Collector]:
    """Seed one cached PR; for example, test a later catalogue transition.

    Returns
    -------
    tuple[RecordingStore, Collector]
        A capture store and the collector seeded with that cached PR.
    """
    store = RecordingStore()
    collector = Collector(typ.cast("Store", store), "workspace", github=False)
    collector.pr_cache[request.url] = request
    return store, collector


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("catalogue_status", "expected_stage"),
    [("merged", "merged"), ("closed", "closed")],
)
@pytest.mark.parametrize("cached_status", ["open", "draft"])
async def test_terminal_catalogue_status_replaces_cached_active_status(
    catalogue_status: str,
    expected_stage: str,
    cached_status: str,
) -> None:
    """A fresh terminal catalogue status wins while the known title survives."""
    store, collector = _collector_with_cached_pr(
        PullRequest(url=PR_URL, status=cached_status, title="Plan: keep this title")
    )

    await collector.reconcile(make_catalogue([PR_URL], catalogue_status))

    request = store.entries[0].pull_requests[0]
    assert request.status == catalogue_status, (
        "Fresh terminal catalogue facts must supersede a cached active status."
    )
    assert request.title == "Plan: keep this title", (
        "A terminal transition must preserve a previously observed PR title."
    )
    assert store.entries[0].stage == expected_stage, (
        "Workflow classification must follow the current terminal PR evidence."
    )


def test_invalid_pr_url_remains_unknown() -> None:
    """Untrusted links never inherit cached facts or a catalogue lifecycle."""
    collector = Collector(typ.cast("Store", RecordingStore()), "workspace")

    assert collector._pr("https://example.invalid/pull/1", "merged") == PullRequest(
        url="",
        status="unknown",
    ), "Untrusted URLs must not gain a known lifecycle or an actionable link."


@pytest.mark.asyncio
async def test_invalid_association_prevents_stage_in_collector_projection() -> None:
    """A valid draft cannot hide an invalid association during reconciliation."""
    store, collector = _collector_with_cached_pr(
        PullRequest(url=PR_URL, status="draft", title="Build")
    )
    catalogue = Catalogue(
        ok=True,
        workspace_id="workspace",
        sessions=[
            RawSession(
                id="session-with-incomplete-prs",
                pull_requests=[
                    RawPR(url=PR_URL, status="draft"),
                    RawPR(url="https://example.invalid/pull/2", status="open"),
                ],
            ),
        ],
    )

    await collector.reconcile(catalogue)

    entry = store.entries[0]
    assert entry.stage == "unclassified", (
        "A rejected URL must not allow the remaining draft to define a stage."
    )
    assert [pr.status for pr in entry.pull_requests] == ["draft", "unknown"], (
        "The projected associations must retain the source uncertainty."
    )


@pytest.mark.asyncio
async def test_nonzero_gh_exit_preserves_valid_partial_graphql_data(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid stdout remains useful when gh also reports GraphQL errors."""
    payload = {
        "data": {
            "p0": {
                "pullRequest": {
                    "title": "Plan: retain this record",
                    "state": "OPEN",
                    "isDraft": False,
                }
            }
        },
        "errors": [{"message": "private diagnostic must not escape"}],
    }
    source = "\n".join([
        f"#!{sys.executable}",
        "import sys",
        "sys.stdin.read()",
        f"print({json.dumps(payload)!r})",
        "raise SystemExit(1)",
        "",
    ])
    executable = fake_gh(tmp_path, source)
    enable_fake_gh(monkeypatch, executable.parent)

    result = await read_pull_requests([PR_URL])

    assert result.records[PR_URL] == PullRequest(
        url=PR_URL,
        status="open",
        title="Plan: retain this record",
    ), "A nonzero CLI exit must preserve usable typed GraphQL records."
    assert result.is_partial is True, "The retained facts must carry a partial warning."
    assert "private diagnostic must not escape" not in repr(result), (
        "Raw GraphQL diagnostics must not survive in the lookup result."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lifecycle_case",
    [
        ("CLOSED", True, "closed"),
        ("MERGED", True, "merged"),
        ("OPEN", True, "draft"),
    ],
)
async def test_terminal_github_state_takes_priority_over_draft_flag(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_case: tuple[str, bool, str],
) -> None:
    """GitHub terminal state wins, while open draft PRs remain drafts."""
    state, is_draft, expected_status = lifecycle_case
    payload = {
        "data": {
            "p0": {
                "pullRequest": {
                    "title": "Late draft-state correction",
                    "state": state,
                    "isDraft": is_draft,
                }
            }
        }
    }
    source = "\n".join([
        f"#!{sys.executable}",
        "import sys",
        "sys.stdin.read()",
        f"print({json.dumps(payload)!r})",
        "",
    ])
    executable = fake_gh(tmp_path, source)
    enable_fake_gh(monkeypatch, executable.parent)

    result = await read_pull_requests([PR_URL])

    assert result.records[PR_URL].status == expected_status, (
        "Terminal lifecycle states must take precedence over the draft flag."
    )
    assert result.is_partial is False, (
        "A complete PR response must remain complete after normalization."
    )


@pytest.mark.asyncio
async def test_failed_middle_batch_preserves_surrounding_results_and_warning(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed forty-item batch does not discard earlier or later batches."""
    counter_path = tmp_path / "calls"
    source = "\n".join([
        f"#!{sys.executable}",
        "import json",
        "import pathlib",
        "import sys",
        "sys.stdin.read()",
        f"counter = pathlib.Path({str(counter_path)!r})",
        "call = int(counter.read_text() or '0') + 1 if counter.exists() else 1",
        "counter.write_text(str(call))",
        "if call == 2:",
        "    print('credential-like diagnostic', file=sys.stderr)",
        "    raise SystemExit(1)",
        "alias_count = 40 if call == 1 else 1",
        "pr = {'title': f'batch-{call}', 'state': 'OPEN', 'isDraft': False}",
        (
            "payload = {'data': {f'p{index}': {'pullRequest': pr} "
            "for index in range(alias_count)}}"
        ),
        "print(json.dumps(payload))",
        "",
    ])
    executable = fake_gh(tmp_path, source)
    enable_fake_gh(monkeypatch, executable.parent)
    urls = sorted(
        f"https://github.com/example/project/pull/{index + 1}" for index in range(81)
    )
    store = RecordingStore()
    collector = Collector(typ.cast("Store", store), "workspace")

    await collector._enrich_prs(make_catalogue(urls))

    assert collector.pr_cache[urls[0]].title == "batch-1", (
        "A later batch failure must not discard earlier successful facts."
    )
    assert urls[40] not in collector.pr_cache, (
        "A failed batch must not fabricate records for inaccessible associations."
    )
    assert collector.pr_cache[urls[80]].title == "batch-3", (
        "A failed batch must not prevent later batches from being queried."
    )
    assert collector.enrichment_error is not None, (
        "Partial enrichment must remain visible as a collector health warning."
    )
    assert "credential-like diagnostic" not in collector.enrichment_error, (
        "The source warning must never expose the CLI's raw diagnostic."
    )
