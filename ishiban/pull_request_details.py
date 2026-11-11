"""Bounded GitHub title and stack enrichment for selected inspector sessions.

For example, PullRequestTitles().read(urls) returns known titles without
reclassifying sessions or writing to the observation journal.
"""

import asyncio
import collections
import dataclasses as dc
import logging
import time
import typing as typ

import msgspec

from ishiban.lody import PR_URL, read_pull_requests
from ishiban.protocol import ProtocolError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from ishiban.lody import GitHubStackFacts, _PullRequestLookup
from ishiban.cache_entries import fresh_cache_entry

MAX_REQUESTED_PR_URLS = 5
MAX_CACHE_ENTRIES = 256
POSITIVE_TTL_SECONDS = 300.0
NEGATIVE_TTL_SECONDS = 30.0
LOOKUP_TIMEOUT_SECONDS = 20.0
LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class _CacheEntry:
    """One bounded positive or negative inspector PR-cache entry."""

    title: str | None
    stack: GitHubStackFacts | None
    expires_at: float


def _requested_pr_urls(urls: list[str]) -> list[str]:
    """Admit the first five distinct GitHub PR URLs for inspector reads.

    This single policy is shared by title lookup and cached stack projection.
    For example, a duplicate URL does not consume a second lookup slot.

    Returns
    -------
    list[str]
        Valid unique URLs in source order, bounded to the inspector limit.
    """
    return list(dict.fromkeys(url for url in urls if PR_URL.fullmatch(url)))[
        :MAX_REQUESTED_PR_URLS
    ]


class PullRequestTitles:
    """Resolve titles only for valid PR URLs requested by the inspector.

    For example, terminal PR titles remain available without changing stage.
    """

    def __init__(
        self,
        *,
        clock: cabc.Callable[[], float] | None = None,
        lookup: cabc.Callable[
            [list[str]], cabc.Coroutine[object, object, _PullRequestLookup]
        ]
        | None = None,
    ) -> None:
        """Bind a clock and read-only adapter to one bounded title cache.

        For example, ``PullRequestTitles(clock=fake_now, lookup=fake_read)``
        keeps expiry and provider responses under test control.
        """
        self._cache: collections.OrderedDict[str, _CacheEntry] = (
            collections.OrderedDict()
        )
        self._lock = asyncio.Lock()
        self._clock = time.monotonic if clock is None else clock
        self._lookup = read_pull_requests if lookup is None else lookup
        self._lookup_timeout = LOOKUP_TIMEOUT_SECONDS

    async def read(self, urls: list[str]) -> dict[str, str]:
        """Return known nonempty titles for the first five valid PR URLs.

        Parameters
        ----------
        urls : list[str]
            Catalogue PR URLs associated with the selected session.

        Returns
        -------
        dict[str, str]
            Available titles keyed by their original validated URLs.
        """
        requested = _requested_pr_urls(urls)
        if not requested:
            return {}
        async with self._lock:
            return await self._read_locked(requested)

    async def stack_for(self, urls: list[str]) -> dict[str, object]:
        """Return cached stack facts for requested URLs without another lookup.

        For example, an inaccessible sibling leaves an explicit gap rather
        than inventing a branch relationship.

        Returns
        -------
        dict[str, object]
            Available typed branch and merge facts keyed by requested URL.
        """
        requested = _requested_pr_urls(urls)
        async with self._lock:
            now = self._clock()
            return {
                url: msgspec.to_builtins(entry.stack)
                for url in requested
                if (entry := fresh_cache_entry(self._cache, url, now=now)) is not None
                and entry.stack is not None
            }

    async def _read_locked(self, urls: list[str]) -> dict[str, str]:
        """Use cache entries and serialize one bounded adapter lookup.

        Returns
        -------
        dict[str, str]
            Available titles from cache and any successful lookup.
        """
        titles, missing = self._read_cache(urls, self._clock())
        if not missing:
            return titles
        lookup = await self._lookup_missing(missing)
        titles.update(self._cache_details(missing, lookup))
        return titles

    def _read_cache(
        self, urls: list[str], now: float
    ) -> tuple[dict[str, str], list[str]]:
        """Separate fresh cached titles from URLs that need a lookup.

        Returns
        -------
        tuple[dict[str, str], list[str]]
            Titles already known and missing URLs in request order.
        """
        titles: dict[str, str] = {}
        missing: list[str] = []
        for url in urls:
            entry = fresh_cache_entry(self._cache, url, now=now)
            if entry is None:
                missing.append(url)
                continue
            if entry.title is not None:
                titles[url] = entry.title
        return titles, missing

    async def _lookup_missing(self, urls: list[str]) -> _PullRequestLookup | None:
        """Read titles through the existing bounded adapter or return no facts.

        Returns
        -------
        _PullRequestLookup | None
            Available adapter facts; expected failures produce no facts.
        """
        # Preserve useful titles without exposing provider diagnostics.
        try:
            async with asyncio.timeout(self._lookup_timeout):
                lookup = await self._lookup(urls)
        except TimeoutError:
            LOGGER.warning("PR titles unavailable category=deadline")
            return None
        except msgspec.DecodeError, ProtocolError:
            LOGGER.warning("PR titles unavailable category=protocol")
            return None
        except OSError:
            LOGGER.warning("PR titles unavailable category=cli")
            return None
        if lookup.is_partial:
            LOGGER.warning("PR titles incomplete category=partial")
        return lookup

    def _cache_details(
        self, urls: list[str], lookup: _PullRequestLookup | None
    ) -> dict[str, str]:
        """Cache title and stack facts, returning only nonempty titles.

        Returns
        -------
        dict[str, str]
            Known titles from this lookup.
        """
        now = self._clock()
        titles: dict[str, str] = {}
        for url in urls:
            record = lookup.records.get(url) if lookup is not None else None
            title = (
                record.title
                if record is not None and record.title and record.title.strip()
                else None
            )
            ttl = POSITIVE_TTL_SECONDS if title is not None else NEGATIVE_TTL_SECONDS
            stack = (lookup.stack or {}).get(url) if lookup is not None else None
            self._cache[url] = _CacheEntry(
                title=title, stack=stack, expires_at=now + ttl
            )
            self._cache.move_to_end(url)
            if title is not None:
                titles[url] = title
            if len(self._cache) > MAX_CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return titles
