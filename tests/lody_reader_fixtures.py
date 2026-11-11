"""Typed keyword options shared by Lody reader test helpers."""

import typing as typ


class LazyActivityResponseOptions(typ.TypedDict, total=False):
    """Optional overrides for a lazy activity response fixture."""

    session_id: str
    workspace_id: str
    ok: bool
    version: int
    state: str
    source: str
    freshness: str
    turn_state: str


class LazyActivityFakeOptions(typ.TypedDict, total=False):
    """Optional timing and concurrency settings for a fake Lody process."""

    linger_after_output: float
    delay_before_output: float
    track_concurrency: bool


class SessionAgentResponseOptions(typ.TypedDict, total=False):
    """Optional overrides for a session agent metadata response."""

    session_id: str
    workspace_id: str
    ok: bool
    agent_type: str | None
    config_id: str | None
