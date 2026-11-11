"""Load agent configuration labels on demand from Lody session metadata."""

import asyncio
import collections
import time

import msgspec

from ishiban import lody
from ishiban.cache_entries import remember_cache_entry
from ishiban.session_show import SessionShowReader, read_show

MAX_CACHE_ENTRIES = 128
SUCCESS_CACHE_SECONDS = 300.0
FAILURE_CACHE_SECONDS = 30.0
CONFIG_TIMEOUT_SECONDS = 30.0
MAX_CONFIGURATION_ID_LENGTH = 256
MAX_CONFIGURATION_NAME_LENGTH = 512


class AgentDetails(msgspec.Struct, rename="camel"):
    """Expose only agent type and configuration identity and label."""

    agent_type: str | None = None
    configuration_id: str | None = None
    configuration_name: str | None = None


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
        show_reader: SessionShowReader | None = None,
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
        self._show_reader = show_reader or SessionShowReader(
            workspace_id, selector, executable
        )
        self._lock = asyncio.Lock()
        self._cache: collections.OrderedDict[
            tuple[str, int],
            tuple[float, AgentDetails | None],
        ] = collections.OrderedDict()

    async def read(self, session_id: str, basis: int = 0) -> AgentDetails | None:
        """Return agent labels without requesting or retaining secret fields.

        For example, a configuration lookup failure preserves the session's
        agent type and configuration ID while leaving the name unavailable.

        Returns
        -------
        AgentDetails or None
            The bounded agent metadata or a safe unavailable marker.
        """
        key = (session_id, basis)
        async with self._lock:
            is_cached, cached = self._cached(key)
            if is_cached:
                return cached
            try:
                session = await self._show_reader.read(session_id, basis)
            except OSError, TimeoutError, lody.ProtocolError, msgspec.DecodeError:
                session = None
            if session is None:
                self._remember(key, None, FAILURE_CACHE_SECONDS)
                return None

            config_id = session.agent_config_id
            if config_id is None:
                details = AgentDetails(agent_type=session.agent_type)
                self._remember(key, details, SUCCESS_CACHE_SECONDS)
                return details
            if not config_id or len(config_id) > MAX_CONFIGURATION_ID_LENGTH:
                details = AgentDetails(agent_type=session.agent_type)
                self._remember(key, details, FAILURE_CACHE_SECONDS)
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
                self._remember(key, partial, FAILURE_CACHE_SECONDS)
                return partial

            details = AgentDetails(
                agent_type=session.agent_type,
                configuration_id=config_id,
                configuration_name=name,
            )
            self._remember(key, details, SUCCESS_CACHE_SECONDS)
            return details

    def _cached(
        self,
        key: tuple[str, int],
    ) -> tuple[bool, AgentDetails | None]:
        """Return an unexpired cache entry and whether the key was present.

        Returns
        -------
        tuple of bool and AgentDetails or None
            Whether the key is cached and its cached value.
        """
        entry = self._cache.get(key)
        if entry is None:
            return False, None
        expires_at, value = entry
        if expires_at <= _monotonic_time():
            del self._cache[key]
            return False, None
        self._cache.move_to_end(key)
        return True, value

    def _remember(
        self,
        key: tuple[str, int],
        value: AgentDetails | None,
        ttl: float,
    ) -> None:
        """Store a short-lived result and evict the least recently used entry."""
        remember_cache_entry(
            self._cache,
            key,
            (_monotonic_time() + ttl, value),
            capacity=MAX_CACHE_ENTRIES,
        )

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
        response = await read_show(
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
