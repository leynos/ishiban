"""Own bounded cache and task lifecycles for read-only Lody metadata calls."""

import asyncio
import collections
import dataclasses
import logging
import typing as typ

import msgspec

from ishiban import lody
from ishiban.cache_entries import fresh_cache_entry, remember_cache_entry
from ishiban.task_ownership import cancel_and_reap, singleflight_task

LOGGER = logging.getLogger(__name__)
CAPACITY_WARNING_INTERVAL_SECONDS = 30.0

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@dataclasses.dataclass(frozen=True, slots=True)
class CachedReadPolicy:
    """Configure one adapter's cache and pending-read limits."""

    capacity: int
    max_inflight: int
    success_seconds: float
    failure_seconds: float


@dataclasses.dataclass(frozen=True, slots=True)
class _CacheEntry[Value]:
    """Retain a successful or unavailable value until its monotonic expiry."""

    expires_at: float
    value: Value | None


class CachedLodyReads[Key, Value]:
    """Share one validated CLI result per key within bounded cache ownership.

    For example, an unavailable observation receives a shorter TTL than a
    verified show result; each adapter supplies its own identity checks and
    subprocess deadline through ``load``.
    """

    def __init__(
        self,
        policy: CachedReadPolicy,
        clock: cabc.Callable[[], float],
        load: cabc.Callable[[Key], cabc.Coroutine[object, object, Value | None]],
    ) -> None:
        """Bind one adapter's policy, clock and verified CLI loader."""
        self._policy = policy
        self._clock = clock
        self._loader = load
        self._cache: collections.OrderedDict[Key, _CacheEntry[Value]] = (
            collections.OrderedDict()
        )
        self._inflight: dict[Key, asyncio.Task[Value | None]] = {}
        self._is_closed = False
        self._next_capacity_warning_at: float | None = None
        self._suppressed_capacity_warnings = 0

    async def read(self, key: Key) -> Value | None:
        """Return a cached or shared verified result, without waiter ownership.

        For example, cancelling one HTTP waiter leaves a shared CLI task
        available to another caller until this service closes.

        Returns
        -------
        Value or None
            A verified result, cached unavailability, or capacity rejection.
        """
        if self._is_closed:
            return None
        entry = fresh_cache_entry(self._cache, key, now=self._clock())
        if entry is not None:
            return entry.value
        task = singleflight_task(
            self._inflight,
            key,
            capacity=self._policy.max_inflight,
            load=self._load,
        )
        if task is None:
            self._warn_capacity()
            return None
        return await asyncio.shield(task)

    def _warn_capacity(self) -> None:
        """Log one fixed-category warning per interval for this reader.

        For example, three rejections at one instant log once; the next
        interval reports the two suppressed warnings without revealing keys.
        """
        now = self._clock()
        next_warning = self._next_capacity_warning_at
        if next_warning is not None and now < next_warning:
            self._suppressed_capacity_warnings += 1
            return
        if self._suppressed_capacity_warnings:
            LOGGER.warning(
                "Lody metadata unavailable category=capacity suppressed=%d",
                self._suppressed_capacity_warnings,
            )
        else:
            LOGGER.warning("Lody metadata unavailable category=capacity")
        self._next_capacity_warning_at = now + CAPACITY_WARNING_INTERVAL_SECONDS
        self._suppressed_capacity_warnings = 0

    async def close(self) -> None:
        """Stop admission, then cancel and reap every owned pending CLI read."""
        if self._is_closed:
            return
        self._is_closed = True
        await cancel_and_reap(self._inflight.values())
        self._inflight.clear()
        self._cache.clear()

    async def _load(self, key: Key) -> Value | None:
        """Map expected CLI failures to short-lived unavailable results.

        Returns
        -------
        Value or None
            Verified adapter output or a bounded failure marker.
        """
        # Exception text can contain credentials or source payloads.
        value = None
        try:
            value = await self._loader(key)
        except TimeoutError:
            LOGGER.warning("Lody metadata unavailable category=deadline")
        except lody.ProtocolError, msgspec.DecodeError:
            LOGGER.warning("Lody metadata unavailable category=protocol")
        except OSError:
            LOGGER.warning("Lody metadata unavailable category=cli")
        lifetime = (
            self._policy.success_seconds
            if value is not None
            else self._policy.failure_seconds
        )
        remember_cache_entry(
            self._cache,
            key,
            _CacheEntry(self._clock() + lifetime, value),
            capacity=self._policy.capacity,
        )
        return value
