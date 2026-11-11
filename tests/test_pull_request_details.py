"""Exercise bounded, cached title lookups for inspector-selected PRs."""

import asyncio
from unittest import mock

import msgspec
import pytest

import ishiban.pull_request_details as details
from ishiban.domain import PullRequest
from ishiban.lody import _PullRequestLookup
from ishiban.protocol import ProtocolError
from ishiban.pull_request_details import PullRequestTitles

URL_ROOT = "https://github.com/example/project/pull/"


def url(number: int) -> str:
    """Return one valid GitHub PR URL for a requested positive number.

    Returns
    -------
    str
        A URL accepted by the existing GitHub adapter.
    """
    return f"{URL_ROOT}{number}"


def lookup_result(
    urls: list[str], *, status: str = "open", title_prefix: str = "Title"
) -> _PullRequestLookup:
    """Build the existing adapter result shape for these bounded URLs.

    Returns
    -------
    _PullRequestLookup
        One known title per requested URL.
    """
    return _PullRequestLookup(
        records={
            request_url: PullRequest(
                url=request_url,
                status=status,
                title=f"{title_prefix} {request_url}",
            )
            for request_url in urls
        },
        is_partial=False,
    )


@pytest.mark.asyncio
async def test_default_lookup_uses_adapter_available_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary API construction path binds the current read-only adapter."""
    requested = [url(1)]
    adapter = mock.AsyncMock(return_value=lookup_result(requested))
    monkeypatch.setattr(details, "read_pull_requests", adapter)

    reader = PullRequestTitles()
    assert await reader.read(requested) == {requested[0]: f"Title {requested[0]}"}, (
        "The ordinary service must use the adapter bound at construction."
    )
    adapter.assert_awaited_once_with(requested)


@pytest.mark.parametrize(
    ("outcome", "category"),
    [
        ("complete", None),
        ("empty", None),
        ("partial", "partial"),
        ("failed", "cli"),
        ("deadline", "deadline"),
        ("protocol", "protocol"),
    ],
)
@pytest.mark.asyncio
async def test_lookup_diagnostics_preserve_partial_titles_and_cache_outcomes(
    caplog: pytest.LogCaptureFixture,
    outcome: str,
    category: str | None,
) -> None:
    """A partial lookup remains visible diagnostically without losing its titles."""
    requested = [url(1), url(2)]
    retained = requested if outcome == "complete" else requested[:1]
    records = (
        lookup_result(retained).records if outcome in {"complete", "partial"} else {}
    )
    failures = {
        "failed": OSError("DO_NOT_LOG_PROVIDER_PAYLOAD"),
        "deadline": TimeoutError("DO_NOT_LOG_PROVIDER_PAYLOAD"),
        "protocol": ProtocolError("DO_NOT_LOG_PROVIDER_PAYLOAD"),
    }
    read = mock.AsyncMock(
        return_value=_PullRequestLookup(
            records=records, is_partial=outcome == "partial"
        ),
        side_effect=failures.get(outcome),
    )
    reader = PullRequestTitles(lookup=read)

    first = await reader.read(requested)

    expected = {request_url: record.title for request_url, record in records.items()}
    assert first == await reader.read(requested) == expected, (
        "Complete, partial and empty results must retain exactly their known "
        "sibling titles."
    )
    assert read.await_count == 1, (
        "Positive and negative cache hits must avoid another lookup."
    )
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == details.__name__
    ]
    expected_messages = (
        []
        if category is None
        else [
            (
                f"PR titles {'incomplete' if category == 'partial' else 'unavailable'} "
                f"category={category}"
            )
        ]
    )
    assert messages == expected_messages, (
        "Only an incomplete or failed external read needs a diagnostic."
    )
    assert "DO_NOT_LOG_PROVIDER_PAYLOAD" not in caplog.text, (
        "Diagnostics must not include provider errors or credentials."
    )
    assert all(request_url not in caplog.text for request_url in requested), (
        "Diagnostic categories must not include pull-request identities."
    )


@pytest.mark.asyncio
async def test_reads_titles_for_terminal_and_active_pull_requests() -> None:
    """Title enrichment does not filter by PR lifecycle status."""
    urls = [url(1), url(2), url(3)]
    records = {
        urls[0]: PullRequest(url=urls[0], status="closed", title="Closed PR"),
        urls[1]: PullRequest(url=urls[1], status="merged", title="Merged PR"),
        urls[2]: PullRequest(url=urls[2], status="draft", title="Draft PR"),
    }
    adapter = mock.AsyncMock(
        return_value=_PullRequestLookup(records=records, is_partial=False)
    )
    titles = await PullRequestTitles(lookup=adapter).read(urls)

    assert titles.get(urls[0]) == "Closed PR", "Closed PR titles must remain available."
    assert titles.get(urls[1]) == "Merged PR", "Merged PR titles must remain available."
    assert titles.get(urls[2]) == "Draft PR", "Active PR titles must remain available."
    assert set(titles) == set(urls), "Only the requested PR titles should be returned."
    adapter.assert_awaited_once_with(urls)


@pytest.mark.asyncio
async def test_ignores_invalid_urls_and_requests_only_first_five_valid() -> None:
    """Untrusted URLs never reach the adapter and each call remains bounded."""
    candidates = [
        "https://evil.invalid/repo/pull/1",
        *[url(number) for number in range(1, 8)],
    ]
    requested = candidates[1:6]
    adapter = mock.AsyncMock(return_value=lookup_result(requested))
    service = PullRequestTitles(lookup=adapter)

    titles = await service.read(candidates)

    adapter.assert_awaited_once_with(requested)
    assert set(titles) == set(requested), (
        "Only the first five valid URLs should resolve."
    )
    assert await service.read(["https://evil.invalid/pull/9"]) == {}, (
        "An invalid URL must not produce a title."
    )
    adapter.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("ttl", "initial_title"), [(300.0, "Title"), (30.0, None)])
async def test_title_cache_uses_positive_and_negative_expiry(
    ttl: float, initial_title: str | None
) -> None:
    """Successful titles and misses expire on their distinct cache schedules."""
    current_time = [100.0]
    initial = (
        lookup_result([url(1)], title_prefix=initial_title)
        if initial_title is not None
        else _PullRequestLookup(records={}, is_partial=True)
    )
    expected = {url(1): f"{initial_title} {url(1)}"} if initial_title else {}
    adapter = mock.AsyncMock(
        side_effect=[initial, lookup_result([url(1)], title_prefix="Refreshed")]
    )

    def clock_now() -> float:
        """Return the controlled monotonic time.

        Returns
        -------
        float
            The mutable cache-test clock value.
        """
        return current_time[0]

    service = PullRequestTitles(clock=clock_now, lookup=adapter)
    assert await service.read([url(1)]) == expected, "Return the initial title or miss."
    current_time[0] += ttl - 0.1
    assert await service.read([url(1)]) == expected, "Reuse the unexpired cache entry."
    adapter.assert_awaited_once()
    current_time[0] += 0.2
    assert await service.read([url(1)]) == {url(1): f"Refreshed {url(1)}"}, (
        "An expired entry must permit a fresh title lookup."
    )
    assert adapter.await_count == 2, "Refresh once after the appropriate TTL."


@pytest.mark.asyncio
async def test_partial_lookup_caches_known_title_and_missing_fact() -> None:
    """Partial adapter results keep known titles and negative-cache only misses."""
    first_url, blank_url, missing_url = url(1), url(2), url(3)
    adapter = mock.AsyncMock(
        return_value=_PullRequestLookup(
            records={
                first_url: PullRequest(
                    url=first_url,
                    status="merged",
                    title="Known despite partial response",
                ),
                blank_url: PullRequest(
                    url=blank_url,
                    status="closed",
                    title="   ",
                ),
            },
            is_partial=True,
        )
    )
    service = PullRequestTitles(lookup=adapter)

    assert await service.read([first_url, blank_url, missing_url]) == {
        first_url: "Known despite partial response"
    }, "Partial results should return only known nonempty titles."
    assert await service.read([first_url, blank_url, missing_url]) == {
        first_url: "Known despite partial response"
    }, "Partial titles and misses should be cached independently."
    adapter.assert_awaited_once_with([first_url, blank_url, missing_url])


@pytest.mark.parametrize(
    "failure",
    [
        OSError("offline"),
        TimeoutError("timeout"),
        msgspec.DecodeError("invalid payload"),
        ProtocolError("invalid lookup"),
    ],
)
@pytest.mark.asyncio
async def test_adapter_failures_return_no_untrusted_title(
    failure: Exception,
) -> None:
    """Expected lookup failures become a short negative cache entry."""
    adapter = mock.AsyncMock(side_effect=failure)
    assert await PullRequestTitles(lookup=adapter).read([url(1)]) == {}, (
        "Expected adapter failures must produce no unverified title."
    )
    adapter.assert_awaited_once_with([url(1)])


@pytest.mark.asyncio
async def test_concurrent_requests_deduplicate_missing_lookup() -> None:
    """A waiter sees the first completed lookup instead of repeating it."""
    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()
    urls = [url(1)]

    async def delayed_lookup(requested: list[str]) -> _PullRequestLookup:
        """Hold one adapter request while the second reader queues.

        Returns
        -------
        _PullRequestLookup
            Successful title records for the single serialized request.
        """
        lookup_started.set()
        await release_lookup.wait()
        return lookup_result(requested)

    adapter = mock.AsyncMock(side_effect=delayed_lookup)
    service = PullRequestTitles(lookup=adapter)

    first = asyncio.create_task(service.read(urls))
    await lookup_started.wait()
    second = asyncio.create_task(service.read(urls))
    release_lookup.set()
    results = await asyncio.gather(first, second)

    assert results == [{urls[0]: f"Title {urls[0]}"}] * 2, (
        "Concurrent readers should observe the same resolved title."
    )
    adapter.assert_awaited_once_with(urls)


@pytest.mark.asyncio
async def test_lru_cache_is_bounded_to_256_titles() -> None:
    """The least recently used title is fetched again after the cache fills."""
    adapter = mock.AsyncMock(side_effect=lookup_result)
    service = PullRequestTitles(lookup=adapter)
    urls = [url(number) for number in range(1, 258)]

    for start in range(0, len(urls), 5):
        await service.read(urls[start : start + 5])

    prior_calls = adapter.await_count
    await service.read([urls[0]])

    assert adapter.await_count == prior_calls + 1, (
        "The least recently used title should be fetched after eviction."
    )
    assert len(service._cache) == 256, (
        "The title cache must remain capped at 256 entries."
    )
