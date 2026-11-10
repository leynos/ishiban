"""Share bounded, verified Lody session-show metadata across lazy readers."""

import asyncio
import dataclasses
import datetime as dt
import re
import time

import msgspec

from ishiban import lody
from ishiban.cached_lody_reads import CachedLodyReads, CachedReadPolicy

MAX_CACHE_ENTRIES = 256
MAX_IN_FLIGHT_READS = 32
MAX_CONCURRENT_SHOWS = 2
SUCCESS_CACHE_SECONDS = 300.0
FAILURE_CACHE_SECONDS = 30.0
SESSION_TIMEOUT_SECONDS = 20.0
MAX_SHOW_LIFETIME_SECONDS = 45.0
MAX_TIMESTAMP_CHARS = 64
ISO_TIMESTAMP = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


@dataclasses.dataclass(frozen=True, slots=True)
class SessionShowMetadata:
    """Retain verified recency and labels without private session payloads."""

    session_id: str
    agent_type: str | None
    agent_config_id: str | None
    latest_history_at: str | None


class _Workspace(msgspec.Struct):
    """Decode the workspace identity returned by session show."""

    id: str


class _Session(msgspec.Struct, rename="camel"):
    """Decode only identity and public agent fields from session show."""

    id: str
    agent_type: str | None = None
    agent_config_id: str | None = None


class _SessionShowResponse(msgspec.Struct, rename="camel"):
    """Decode the bounded session-show envelope and outer history time."""

    ok: bool
    workspace: _Workspace
    session: _Session
    latest_history_at: str | None = None


def _monotonic_time() -> float:
    """Return seconds for TTL expiry without changing the event-loop clock.

    Returns
    -------
    float
        The current monotonic time.
    """
    return time.monotonic()


async def read_show[T](
    command: tuple[str, ...],
    response_type: type[T],
    deadline_seconds: float,
    *,
    allow_transport_logs: bool = False,
) -> T:
    """Decode one bounded CLI show envelope for caller identity checks.

    For example, configuration reads may permit Lody's known transport logs.

    Returns
    -------
    T
        A typed envelope whose identity the caller must still validate.
    """
    data = await lody.read_json_object(
        command,
        deadline_seconds=deadline_seconds,
        allow_transport_logs=allow_transport_logs,
    )
    return msgspec.json.decode(data, type=response_type)


def _valid_history_time(value: str | None) -> str | None:
    """Retain an aware ISO timestamp only; an invalid value is unavailable.

    Returns
    -------
    str or None
        The original safe timestamp or no usable history time.
    """
    if value is None or len(value) > MAX_TIMESTAMP_CHARS:
        return None
    if ISO_TIMESTAMP.fullmatch(value) is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None


class SessionShowReader:
    """Own two shared metadata children and revision-keyed TTL results.

    For example, inspector and family recency reads for one unchanged tab
    share a single Lody command, while a newer execution watermark rereads it.
    """

    def __init__(
        self, workspace_id: str, selector: str, executable: str = "lody"
    ) -> None:
        """Bind command execution and response identities to one workspace."""
        self._workspace_id = workspace_id
        self._selector = selector
        self._executable = executable
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_SHOWS)
        self._reads = CachedLodyReads[tuple[str, int], SessionShowMetadata](
            CachedReadPolicy(
                capacity=MAX_CACHE_ENTRIES,
                max_inflight=MAX_IN_FLIGHT_READS,
                success_seconds=SUCCESS_CACHE_SECONDS,
                failure_seconds=FAILURE_CACHE_SECONDS,
            ),
            _monotonic_time,
            self._load,
        )

    async def read(self, session_id: str, basis: int = 0) -> SessionShowMetadata | None:
        """Return one verified result, sharing work at an execution watermark.

        For example, ``read("child", 40)`` reuses a cached result until the
        child reaches a newer activity event or its TTL expires.

        Returns
        -------
        SessionShowMetadata or None
            Verified safe fields, or an unavailable result.
        """
        return await self._reads.read((session_id, basis))

    async def close(self) -> None:
        """Cancel and reap owned show children when the API worker stops."""
        await self._reads.close()

    async def _load(self, key: tuple[str, int]) -> SessionShowMetadata | None:
        """Include semaphore wait and CLI execution in one total deadline.

        Returns
        -------
        SessionShowMetadata or None
            Verified show metadata or an unavailable result.
        """
        session_id, _basis = key
        async with asyncio.timeout(MAX_SHOW_LIFETIME_SECONDS):
            async with self._semaphore:
                return await self._read_session(session_id)

    async def _read_session(self, session_id: str) -> SessionShowMetadata | None:
        """Verify Lody's workspace and session before retaining public fields.

        Returns
        -------
        SessionShowMetadata or None
            Safe metadata for the requested identity only.

        Raises
        ------
        lody.ProtocolError
            If Lody supplies a malformed history timestamp.
        """
        command = (
            self._executable,
            "session",
            "show",
            session_id,
            "--workspace",
            self._selector,
            "--json",
        )
        response = await read_show(
            command, _SessionShowResponse, SESSION_TIMEOUT_SECONDS
        )
        if response.ok is not True:
            return None
        if response.workspace.id != self._workspace_id:
            return None
        if response.session.id != session_id:
            return None
        history_time = _valid_history_time(response.latest_history_at)
        if response.latest_history_at is not None and history_time is None:
            message = "Session history time is not an aware ISO timestamp."
            raise lody.ProtocolError(message)
        return SessionShowMetadata(
            session_id=session_id,
            agent_type=response.session.agent_type,
            agent_config_id=response.session.agent_config_id,
            latest_history_at=history_time,
        )
