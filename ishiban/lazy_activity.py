"""Read current persisted activity from Lody only when a caller needs it."""

import asyncio
import collections
import dataclasses
import time

import msgspec

from ishiban import domain
from ishiban.lody import read_json_object
from ishiban.protocol import SESSION_STATES, TURN_STATES, ProtocolError

MAX_OBSERVE_BYTES = 1_048_576
MAX_CACHE_ENTRIES = 256
SUCCESS_CACHE_SECONDS = 300.0
FAILURE_CACHE_SECONDS = 30.0
MAX_CONCURRENT_OBSERVERS = 4
MAX_IN_FLIGHT_OBSERVATIONS = 64
MAX_OBSERVATION_LIFETIME_SECONDS = 45.0
DEFAULT_TIMEOUT_SECONDS = 20.0

type _SessionKey = tuple[str, int]


class _ObserveResponse(msgspec.Struct, rename="camel", forbid_unknown_fields=True):
    """Decode the singular response returned by ``lody session observe``."""

    ok: bool
    version: int
    workspace_id: str
    session: msgspec.Raw


@dataclasses.dataclass(frozen=True, slots=True)
class _CacheEntry:
    """Hold one bounded result and its monotonic expiry time."""

    value: domain.ObservedSession | None
    expires_at: float


def _monotonic_time() -> float:
    """Return monotonic seconds for cache expiry without using wall-clock time.

    Returns
    -------
    float
        Monotonic seconds suitable for measuring elapsed time.
    """
    return time.monotonic()


def _is_persisted_activity(session: domain.ObservedSession, session_id: str) -> bool:
    """Accept only matching, persisted activity with known protocol vocabularies.

    For example, an ``unknown`` state or metadata-only projection is not
    evidence that a session is active.

    Returns
    -------
    bool
        Whether the observation is persisted activity for the requested session.
    """
    if session.session_id != session_id:
        return False
    if session.source != "persisted":
        return False
    if session.state not in SESSION_STATES or session.state == "unknown":
        return False
    if session.freshness not in {"synced", "unavailable"}:
        return False
    turns = list(session.active_turns)
    if session.latest_turn is not None:
        turns.append(session.latest_turn)
    return all(turn.state in TURN_STATES and bool(turn.user_turn_id) for turn in turns)


class LazyActivity:
    """Fetch on-demand session facts with bounded process and cache ownership.

    For example, two reads of the same revision share one Lody subprocess,
    while unrelated reads use at most four subprocesses.
    """

    def __init__(
        self,
        workspace_id: str,
        selector: str,
        executable: str = "lody",
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Configure one workspace-bound observer service.

        Parameters
        ----------
        workspace_id : str
            Expected workspace identity returned by Lody.
        selector : str
            Workspace selector passed as one CLI argument.
        executable : str, default ``"lody"``
            Lody executable or a test executable path.
        timeout : float, default 20 seconds
            Maximum run time for one observer subprocess after it starts.
        """
        self._workspace_id = workspace_id
        self._selector = selector
        self._executable = executable
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_OBSERVERS)
        self._cache: collections.OrderedDict[_SessionKey, _CacheEntry] = (
            collections.OrderedDict()
        )
        self._inflight: dict[
            _SessionKey,
            asyncio.Task[domain.ObservedSession | None],
        ] = {}
        self._is_closed = False

    async def read(
        self,
        session_id: str,
        revision: int,
    ) -> domain.ObservedSession | None:
        """Return cached or freshly observed activity for one revision.

        For example, an unavailable CLI response returns ``None`` and is
        briefly cached to prevent repeated retry bursts.

        Returns
        -------
        ObservedSession or None
            The persisted observation or an unavailable marker.
        """
        if self._is_closed:
            return None
        key = (session_id, revision)
        now = _monotonic_time()
        entry = self._cache.get(key)
        if entry is not None:
            if entry.expires_at > now:
                self._cache.move_to_end(key)
                return entry.value
            del self._cache[key]

        task = self._inflight.get(key)
        if task is None:
            if len(self._inflight) >= MAX_IN_FLIGHT_OBSERVATIONS:
                return None
            task = asyncio.create_task(self._load(key))
            self._inflight[key] = task
        # One cancelled request must not cancel a shared observer needed by
        # other waiters; close() owns cancellation of the shared task itself.
        return await asyncio.shield(task)

    async def close(self) -> None:
        """Cancel and reap every observer owned by this service.

        For example, a Falcon shutdown can await this method to terminate
        hanging CLI children before the application event loop closes.
        """
        if self._is_closed:
            return
        self._is_closed = True
        tasks = tuple(self._inflight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight.clear()
        self._cache.clear()

    async def _load(self, key: _SessionKey) -> domain.ObservedSession | None:
        """Observe and cache one key, mapping expected boundary failures to None.

        Returns
        -------
        ObservedSession or None
            The persisted observation or an unavailable marker.
        """
        session_id, _revision = key
        try:
            try:
                value = await self._observe(session_id)
            except OSError, TimeoutError, ProtocolError, msgspec.DecodeError:
                value = None
            ttl = SUCCESS_CACHE_SECONDS if value is not None else FAILURE_CACHE_SECONDS
            self._remember(key, value, ttl)
            return value
        finally:
            self._inflight.pop(key, None)

    async def _observe(self, session_id: str) -> domain.ObservedSession | None:
        """Run one bounded, shell-free Lody observation.

        Returns
        -------
        ObservedSession or None
            The validated persisted observation, if available.
        """
        command = (
            self._executable,
            "session",
            "observe",
            session_id,
            "--workspace",
            self._selector,
            "--json",
        )
        async with asyncio.timeout(MAX_OBSERVATION_LIFETIME_SECONDS):
            async with self._semaphore:
                return await self._read_response(command, session_id)

    async def _read_response(
        self,
        command: tuple[str, ...],
        session_id: str,
    ) -> domain.ObservedSession | None:
        """Read a complete root object before the CLI transport necessarily exits.

        Returns
        -------
        ObservedSession or None
            The validated persisted observation, if available.

        """
        data = await read_json_object(
            command, max_bytes=MAX_OBSERVE_BYTES, deadline_seconds=self._timeout
        )
        return self._decode_response(data, session_id)

    def _decode_response(
        self,
        data: bytes,
        session_id: str,
    ) -> domain.ObservedSession | None:
        """Decode and check workspace, protocol version, and persisted evidence.

        Returns
        -------
        ObservedSession or None
            The validated persisted observation, if available.
        """
        response = msgspec.json.decode(data, type=_ObserveResponse)
        if response.ok is not True:
            return None
        if response.version != 1:
            return None
        if response.workspace_id != self._workspace_id:
            return None
        session = msgspec.json.decode(
            response.session,
            type=domain.ObservedSession,
        )
        if not _is_persisted_activity(session, session_id):
            return None
        return session

    def _remember(
        self,
        key: _SessionKey,
        value: domain.ObservedSession | None,
        ttl: float,
    ) -> None:
        """Store one success or short-lived miss while enforcing the LRU bound."""
        self._cache[key] = _CacheEntry(
            value=value,
            expires_at=_monotonic_time() + ttl,
        )
        self._cache.move_to_end(key)
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)
