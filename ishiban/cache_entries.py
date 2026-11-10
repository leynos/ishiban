"""Share expiry and LRU reads between on-demand activity and PR-title caches."""

import typing as typ

if typ.TYPE_CHECKING:
    import collections


class ExpiringEntry(typ.Protocol):
    """Expose only the monotonic expiry required for a cache read."""

    @property
    def expires_at(self) -> float:
        """Monotonic expiry; for example, 20.0 is stale when the clock reaches 20.0."""
        ...


def fresh_cache_entry[Key, Entry: ExpiringEntry](
    entries: collections.OrderedDict[Key, Entry], key: Key, *, now: float
) -> Entry | None:
    """Return and touch a live entry, removing one that has expired.

    For example, an entry expiring at 20.0 is a miss when ``now=20.0``.
    The caller retains ownership of values, capacity, clocks and TTL policy.

    Returns
    -------
    Entry or None
        The live entry, including an entry whose payload is a cached miss.
    """
    entry = entries.get(key)
    if entry is None:
        return None
    if entry.expires_at <= now:
        del entries[key]
        return None
    entries.move_to_end(key)
    return entry
