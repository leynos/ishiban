"""Encode journal JSON, read projection fields, and generate UTC timestamps."""

import datetime as dt

import msgspec.json as msjson


def encode_json(value: object) -> str:
    """Encode a validated value as compact UTF-8 JSON text.

    Returns
    -------
    str
        The compact JSON text stored in SQLite.
    """
    return msjson.encode(value).decode("utf-8")


def decode_object(value: str) -> dict[str, object]:
    """Decode a JSON object without accepting a non-object top-level value.

    Returns
    -------
    dict[str, object]
        The decoded JSON object.
    """
    return msjson.decode(value.encode("utf-8"), type=dict[str, object])


def string_field(projection: dict[str, object], key: str) -> str:
    """Read a required string from a decoded projection.

    Returns
    -------
    str
        The string value, or an empty string when the field is missing.

    Examples
    --------
    >>> string_field({"sessionId": "s1"}, "sessionId")
    's1'
    """
    return optional_string_field(projection, key) or ""


def optional_string_field(projection: dict[str, object], key: str) -> str | None:
    """Read an optional string from a decoded projection.

    Returns
    -------
    str or None
        The string value, or ``None`` when the field is missing or non-string.

    Examples
    --------
    >>> optional_string_field({"assistantTurnId": "a1"}, "assistantTurnId")
    'a1'
    >>> optional_string_field({}, "assistantTurnId") is None
    True
    """
    value = projection.get(key)
    return value if isinstance(value, str) else None


def utc_timestamp() -> str:
    """Return a millisecond-precision UTC timestamp for journal metadata.

    Returns
    -------
    str
        An ISO-8601 timestamp with an explicit UTC offset.

    Examples
    --------
    >>> utc_timestamp().endswith("+00:00")
    True
    """
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")
