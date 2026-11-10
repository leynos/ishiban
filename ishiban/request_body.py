"""Bound HTTP request bodies before endpoint-specific JSON decoding."""

import typing as typ

import falcon

if typ.TYPE_CHECKING:
    from falcon import asgi


async def read_bounded_body(
    req: asgi.Request, *, max_bytes: int, error_message: str
) -> bytes:
    """Read a complete HTTP body within the caller's independently owned limit.

    For example, interface preferences pass 1,024 bytes while activity batches
    pass 8,192; a declared or streamed excess raises HTTP 413 before decoding.

    Returns
    -------
    bytes
        The complete body within the endpoint's byte budget.

    Raises
    ------
    falcon.HTTPContentTooLarge
        If the declared or streamed body exceeds ``max_bytes``.
    """
    if req.content_length is not None and req.content_length > max_bytes:
        raise falcon.HTTPContentTooLarge(description=error_message)
    body = bytearray()
    async for chunk in req.stream:
        if len(body) + len(chunk) > max_bytes:
            raise falcon.HTTPContentTooLarge(description=error_message)
        body.extend(chunk)
    return bytes(body)
