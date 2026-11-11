"""Validate exact raw IDs shared by bounded public session read routes."""

MAX_SESSION_ID_CHARS = 256


def is_safe_session_id(session_id: str) -> bool:
    """Accept one nonempty bounded ID without normalizing its characters.

    For example, ``".."`` is valid when carried in a query or JSON body.

    Returns
    -------
    bool
        Whether the raw ID fits the observer request contract.
    """
    return (
        bool(session_id)
        and len(session_id) <= MAX_SESSION_ID_CHARS
        and "\0" not in session_id
    )
