"""Load agent configuration labels on demand from Lody session metadata."""

import asyncio
import collections
import time

import msgspec

from ishiban import lody

MAX_CACHE_ENTRIES = 128
SUCCESS_CACHE_SECONDS = 300.0
FAILURE_CACHE_SECONDS = 30.0
SESSION_TIMEOUT_SECONDS = 20.0
CONFIG_TIMEOUT_SECONDS = 30.0
MAX_CONFIGURATION_ID_LENGTH = 256
MAX_CONFIGURATION_NAME_LENGTH = 512


class AgentDetails(msgspec.Struct, rename="camel"):
    """Expose only agent type and configuration identity and label."""

    agent_type: str | None = None
    configuration_id: str | None = None
    configuration_name: str | None = None


class _Workspace(msgspec.Struct):
    """Decode the workspace identity returned by session show."""

    id: str


class _SessionMetadata(msgspec.Struct, rename="camel"):
    """Decode only the Lody session identity and agent metadata fields."""

    id: str
    agent_type: str | None = None
    agent_config_id: str | None = None


class _SessionShowResponse(msgspec.Struct, rename="camel"):
    """Decode the bounded envelope returned by session show."""

    ok: bool
    workspace: _Workspace
    session: _SessionMetadata


class _AgentConfig(msgspec.Struct, rename="camel"):
    """Decode only configuration identity and its display name."""

    id: str
    name: str


class _AgentConfigShowResponse(msgspec.Struct, rename="camel"):
    """Decode the bounded envelope returned by agent-config show."""

    ok: bool
    workspace_id: str
    agent_config: _AgentConfig


def _monotonic_time() -> float:
    """Return monotonic seconds for cache expiry.

    Returns
    -------
    float
        Monotonic seconds suitable for measuring elapsed time.
    """
    return time.monotonic()


async def _read_show[T](
    command: tuple[str, ...],
    response_type: type[T],
    deadline_seconds: float,
    *,
    allow_transport_logs: bool = False,
) -> T:
    """Decode a bounded Lody show envelope without relaxing caller identity checks.

    For example, configuration reads may permit known transport chatter while
    both callers validate the returned workspace and requested object ID.

    Returns
    -------
    T
        The typed Lody envelope for caller-specific identity validation.
    """
    data = await lody.read_json_object(
        command,
        deadline_seconds=deadline_seconds,
        allow_transport_logs=allow_transport_logs,
    )
    return msgspec.json.decode(data, type=response_type)


class SessionAgentDetails:
    """Read a session's agent labels with one serialized CLI pipeline.

    For example, concurrent reads for one session share the result cached by
    the first complete session and configuration lookup.
    """

    def __init__(
        self,
        workspace_id: str,
        selector: str,
        executable: str = "lody",
    ) -> None:
        """Bind metadata reads to a workspace and CLI selector.

        Parameters
        ----------
        workspace_id : str
            Expected workspace identity returned by both Lody commands.
        selector : str
            Workspace selector passed as one CLI argument.
        executable : str, default ``"lody"``
            Lody executable or a test executable path.
        """
        self._workspace_id = workspace_id
        self._selector = selector
        self._executable = executable
        self._lock = asyncio.Lock()
        self._cache: collections.OrderedDict[
            str,
            tuple[float, AgentDetails | None],
        ] = collections.OrderedDict()

    async def read(self, session_id: str) -> AgentDetails | None:
        """Return agent labels without requesting or retaining secret fields.

        For example, a configuration lookup failure preserves the session's
        agent type and configuration ID while leaving the name unavailable.

        Returns
        -------
        AgentDetails or None
            The bounded agent metadata or a safe unavailable marker.
        """
        async with self._lock:
            is_cached, cached = self._cached(session_id)
            if is_cached:
                return cached
            try:
                session = await self._read_session(session_id)
            except OSError, TimeoutError, lody.ProtocolError, msgspec.DecodeError:
                session = None
            if session is None:
                self._remember(session_id, None, FAILURE_CACHE_SECONDS)
                return None

            config_id = session.agent_config_id
            if config_id is None:
                details = AgentDetails(agent_type=session.agent_type)
                self._remember(session_id, details, SUCCESS_CACHE_SECONDS)
                return details
            if not config_id or len(config_id) > MAX_CONFIGURATION_ID_LENGTH:
                details = AgentDetails(agent_type=session.agent_type)
                self._remember(session_id, details, FAILURE_CACHE_SECONDS)
                return details

            partial = AgentDetails(
                agent_type=session.agent_type,
                configuration_id=config_id,
            )
            try:
                name = await self._read_configuration_name(config_id)
            except OSError, TimeoutError, lody.ProtocolError, msgspec.DecodeError:
                name = None
            if name is None:
                self._remember(session_id, partial, FAILURE_CACHE_SECONDS)
                return partial

            details = AgentDetails(
                agent_type=session.agent_type,
                configuration_id=config_id,
                configuration_name=name,
            )
            self._remember(session_id, details, SUCCESS_CACHE_SECONDS)
            return details

    def _cached(
        self,
        session_id: str,
    ) -> tuple[bool, AgentDetails | None]:
        """Return an unexpired cache entry and whether the key was present.

        Returns
        -------
        tuple of bool and AgentDetails or None
            Whether the key is cached and its cached value.
        """
        entry = self._cache.get(session_id)
        if entry is None:
            return False, None
        expires_at, value = entry
        if expires_at <= _monotonic_time():
            del self._cache[session_id]
            return False, None
        self._cache.move_to_end(session_id)
        return True, value

    def _remember(
        self,
        session_id: str,
        value: AgentDetails | None,
        ttl: float,
    ) -> None:
        """Store a short-lived result and evict the least recently used entry."""
        self._cache[session_id] = (_monotonic_time() + ttl, value)
        self._cache.move_to_end(session_id)
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)

    async def _read_session(self, session_id: str) -> _SessionMetadata | None:
        """Read and verify one workspace-bound Lody session envelope.

        Returns
        -------
        _SessionMetadata or None
            Verified session metadata or an unavailable marker.
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
        response = await _read_show(
            command, _SessionShowResponse, SESSION_TIMEOUT_SECONDS
        )
        if response.ok is not True:
            return None
        if response.workspace.id != self._workspace_id:
            return None
        if response.session.id != session_id:
            return None
        return response.session

    async def _read_configuration_name(self, config_id: str) -> str | None:
        """Read a configuration name after verifying its workspace and ID.

        Returns
        -------
        str or None
            The bounded display name or an unavailable marker.
        """
        command = (
            self._executable,
            "agent-config",
            "show",
            config_id,
            "--workspace",
            self._selector,
            "--json",
        )
        response = await _read_show(
            command,
            _AgentConfigShowResponse,
            CONFIG_TIMEOUT_SECONDS,
            allow_transport_logs=True,
        )
        if response.ok is not True:
            return None
        if response.workspace_id != self._workspace_id:
            return None
        if response.agent_config.id != config_id:
            return None
        return response.agent_config.name[:MAX_CONFIGURATION_NAME_LENGTH]
