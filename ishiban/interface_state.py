"""Signed browser-local interface state, independent of the observation journal.

For example, InterfaceStateCookies(key).read(req) restores density and
presentation without consulting persistent session data.
"""

import os
import pathlib
import secrets
import stat
import tempfile
import typing as typ

import falcon
import msgspec
from falcon import asgi
from itsdangerous import BadData, URLSafeTimedSerializer

COOKIE_NAME = "ishiban_interface_state"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60
COOKIE_SALT = "ishiban.interface-state.v1"
MAX_REQUEST_BYTES = 1024
MAX_REQUEST_ERROR = "Interface state request exceeds 1,024 bytes."
SIGNING_KEY_FILENAME = "interface-state.key"
SIGNING_KEY_BYTES = 32
SIGNING_KEY_MODE = 0o600
DENSITIES = frozenset({"overview", "compact", "balanced", "roomy", "comfortable"})
PRESENTATIONS = frozenset({"panorama", "matrix", "list"})
type Density = typ.Literal["overview", "compact", "balanced", "roomy", "comfortable"]
type Presentation = typ.Literal["panorama", "matrix", "list"]


class InterfaceState(msgspec.Struct, forbid_unknown_fields=True, frozen=True):
    """Validated display controls; defaults to overview panorama."""

    density: Density = "overview"
    presentation: Presentation = "panorama"

    def __post_init__(self) -> None:
        """Reject invalid direct construction as well as decoded values.

        Raises
        ------
        ValueError
            If either field is outside the declared interface-state enums.
        """
        if self.density not in DENSITIES or self.presentation not in PRESENTATIONS:
            raise ValueError


class _MessagePackAdapter:
    """Encode signed state with MessagePack while keeping the cookie URL-safe."""

    dumps = staticmethod(msgspec.msgpack.encode)
    loads = staticmethod(msgspec.msgpack.decode)


class InterfaceStateCookies:
    """Read and issue the single signed interface-state cookie.

    For example, a missing, expired or malformed cookie returns default state.
    """

    def __init__(self, secret: bytes) -> None:
        """Create a timed serializer for one persistent application secret."""
        self._serializer = URLSafeTimedSerializer(
            secret_key=secret,
            salt=COOKIE_SALT,
            serializer=_MessagePackAdapter(),
        )

    def read(self, req: asgi.Request) -> InterfaceState:
        """Return validated cookie state or defaults for any invalid token.

        Parameters
        ----------
        req : falcon.asgi.Request
            Request whose browser cookie may contain the interface state.

        Returns
        -------
        InterfaceState
            Valid density and presentation values, or their defaults.
        """
        token = req.cookies.get(COOKIE_NAME)
        if not token:
            return InterfaceState()
        try:
            payload = self._serializer.loads(token, max_age=COOKIE_MAX_AGE)
            return msgspec.convert(payload, type=InterfaceState)
        except BadData, msgspec.DecodeError, TypeError:
            return InterfaceState()

    def _set_cookie(
        self, resp: asgi.Response, state: InterfaceState, *, secure: bool
    ) -> None:
        """Sign the pair once and set the browser's bounded one-year cookie."""
        encoded = typ.cast("str | bytes", self._serializer.dumps(_state_mapping(state)))
        value = encoded.decode("ascii") if isinstance(encoded, bytes) else encoded
        resp.set_cookie(
            COOKIE_NAME,
            value,
            max_age=COOKIE_MAX_AGE,
            path="/",
            secure=secure,
            http_only=True,
            same_site="Lax",
        )


class InterfaceStateResource:
    """Read or update display controls without writing to the journal."""

    def __init__(self, cookies: InterfaceStateCookies) -> None:
        """Retain the signer for restoring saved browser controls."""
        self.cookies = cookies

    async def on_get(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Return the decoded browser-local state without changing its cookie."""
        resp.media = _state_mapping(self.cookies.read(req))

    async def on_post(self, req: asgi.Request, resp: asgi.Response) -> None:
        """Validate a bounded JSON update and issue its signed cookie.

        Raises
        ------
        falcon.HTTPBadRequest
            If the body is malformed or contains unsupported enum values.
        falcon.HTTPContentTooLarge
            If the request body exceeds 1,024 bytes.
        falcon.HTTPUnsupportedMediaType
            If the request is not application/json.
        """
        if req.content_type != "application/json":
            raise falcon.HTTPUnsupportedMediaType
        if req.content_length is not None and req.content_length > MAX_REQUEST_BYTES:
            raise falcon.HTTPContentTooLarge(description=MAX_REQUEST_ERROR)
        body = await _read_bounded_body(req)
        try:
            state = msgspec.json.decode(body, type=InterfaceState)
        except msgspec.DecodeError as error:
            message = "Interface state must contain supported display values."
            raise falcon.HTTPBadRequest(description=message) from error
        self.cookies._set_cookie(resp, state, secure=req.scheme == "https")
        resp.media = _state_mapping(state)


async def _read_bounded_body(req: asgi.Request) -> bytes:
    """Read at most 1,025 bytes so oversized bodies fail before decoding.

    For example, 1,024 bytes are accepted for validation and the next byte is
    enough to reject the request.

    Returns
    -------
    bytes
        The complete request body after the size check.

    Raises
    ------
    falcon.HTTPContentTooLarge
        If the request exceeds the configured byte limit.
    """
    body = bytearray()
    async for chunk in req.stream:
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise falcon.HTTPContentTooLarge(description=MAX_REQUEST_ERROR)
        body.extend(chunk)
    return bytes(body)


def _state_mapping(state: InterfaceState) -> dict[str, str]:
    """Return only the two stable, public controls.

    Returns
    -------
    dict[str, str]
        The density and presentation values suitable for JSON responses.
    """
    return {"density": state.density, "presentation": state.presentation}


def load_signing_key(directory: pathlib.Path) -> bytes:
    """Load or atomically create a private 32-byte cookie-signing key.

    Parameters
    ----------
    directory : pathlib.Path
        Private local state directory for the running workspace.

    Returns
    -------
    bytes
        The persistent 32-byte signing secret.

    Examples
    --------
    >>> len(load_signing_key(Path(".state")))
    32
    """
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key_path = directory / SIGNING_KEY_FILENAME
    stored_key = _read_signing_key(key_path)
    if stored_key is not None:
        return stored_key

    candidate = secrets.token_bytes(SIGNING_KEY_BYTES)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".interface-state-key-",
        dir=directory,
    )
    temporary_path = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(candidate)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_path, key_path)
        except FileExistsError:
            winner = _read_signing_key(key_path)
            if winner is None:
                return load_signing_key(directory)
            return winner
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return candidate
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_signing_key(path: pathlib.Path) -> bytes | None:
    """Read an existing regular key and enforce its exact private permissions.

    Returns
    -------
    bytes or None
        The stored key, or None if another caller may create it.

    Raises
    ------
    ValueError
        If the existing file is not regular or does not contain 32 bytes.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as existing:
        metadata = os.fstat(existing.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError
        key = existing.read(SIGNING_KEY_BYTES + 1)
        if len(key) != SIGNING_KEY_BYTES:
            raise ValueError
        if stat.S_IMODE(metadata.st_mode) != SIGNING_KEY_MODE:
            os.fchmod(existing.fileno(), SIGNING_KEY_MODE)
        return key
