"""Read current persisted activity from Lody only when a caller needs it."""

import asyncio
import time

import msgspec

from ishiban import domain
from ishiban.cached_lody_reads import CachedLodyReads, CachedReadPolicy
from ishiban.lody import read_json_object
from ishiban.protocol import SESSION_STATES, TURN_STATES

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
    return _has_valid_turns(session)


def _has_valid_turns(session: domain.ObservedSession) -> bool:
    """Validate supplied turns; for example, metadata may omit every turn.

    Returns
    -------
    bool
        Whether every supplied turn has a known state and identity.
    """
    turns = [*session.active_turns]
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
        self._reads = CachedLodyReads[_SessionKey, domain.ObservedSession](
            CachedReadPolicy(
                capacity=MAX_CACHE_ENTRIES,
                max_inflight=MAX_IN_FLIGHT_OBSERVATIONS,
                success_seconds=SUCCESS_CACHE_SECONDS,
                failure_seconds=FAILURE_CACHE_SECONDS,
            ),
            _monotonic_time,
            self._load,
        )

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
        return await self._reads.read((session_id, revision))

    async def close(self) -> None:
        """Cancel and reap every observer owned by this service.

        For example, Falcon shutdown terminates pending CLI children before
        the application event loop closes.
        """
        await self._reads.close()

    async def _load(self, key: _SessionKey) -> domain.ObservedSession | None:
        """Run one bounded observation for the requested execution revision.

        Returns
        -------
        ObservedSession or None
            The validated persisted observation, if available.
        """
        session_id, _revision = key
        return await self._observe(session_id)

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
