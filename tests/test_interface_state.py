"""Exercise signed interface-state cookies through Falcon's ASGI boundary."""

import base64
import concurrent.futures
import http.cookies
import json
import stat
import typing as typ
import zlib

import falcon
import msgspec
import pytest
from falcon import asgi, testing
from itsdangerous import TimestampSigner

from ishiban.interface_state import (
    COOKIE_NAME,
    SIGNING_KEY_FILENAME,
    InterfaceState,
    InterfaceStateCookies,
    InterfaceStateResource,
    load_signing_key,
)

if typ.TYPE_CHECKING:
    import pathlib


SECRET = b"i" * 32
DEFAULT_STATE = {"density": "overview", "presentation": "panorama"}


def make_app(cookies: InterfaceStateCookies) -> asgi.App:
    """Build a one-route Falcon app for exercising the state resource.

    Returns
    -------
    asgi.App
        A local ASGI app with no journal or collector dependencies.
    """
    app = asgi.App()
    app.add_route("/api/v1/interface-state", InterfaceStateResource(cookies))
    return app


def parse_cookie(header_value: str) -> http.cookies.Morsel[str]:
    """Parse one Set-Cookie header into semantic cookie attributes.

    Returns
    -------
    http.cookies.Morsel[str]
        The signed value and parsed attributes for the interface-state cookie.
    """
    parsed = http.cookies.SimpleCookie()
    parsed.load(header_value)
    return parsed[COOKIE_NAME]


def signed_token(cookies: InterfaceStateCookies, payload: object) -> str:
    """Serialize one fixture payload using the production cookie signer.

    Returns
    -------
    str
        ASCII URL-safe signed token accepted by a Cookie header.
    """
    encoded = typ.cast("str | bytes", cookies._serializer.dumps(payload))
    return encoded.decode("ascii") if isinstance(encoded, bytes) else encoded


def tamper_signed_token(token: str) -> str:
    """Corrupt one signature character while preserving token structure.

    Returns
    -------
    str
        A structurally valid token with an invalid signature.
    """
    prefix, signature = token.rsplit(".", 1)
    replacement = "A" if signature[0] != "A" else "B"
    return f"{prefix}.{replacement}{signature[1:]}"


def ancient_timestamp(_signer: TimestampSigner) -> int:
    """Make a signed test token old enough to expire.

    Returns
    -------
    int
        An old Unix timestamp used for expiry validation.
    """
    return 1


def cookie_messagepack_payload(token: str) -> bytes:
    """Decode the URL-safe payload segment from one signed cookie.

    Returns
    -------
    bytes
        MessagePack payload, decompressed when ItsDangerous compressed it.
    """
    compressed = token.startswith(".")
    encoded_payload = token.removeprefix(".").split(".", 1)[0]
    payload = base64.urlsafe_b64decode(
        encoded_payload + "=" * (-len(encoded_payload) % 4)
    )
    return zlib.decompress(payload) if compressed else payload


@pytest.mark.asyncio
async def test_missing_cookie_returns_default_state_without_writing_cookie() -> None:
    """A new browser starts with the default controls and no cookie mutation."""
    cookies = InterfaceStateCookies(SECRET)
    async with testing.ASGIConductor(make_app(cookies)) as conductor:
        response = await conductor.simulate_get("/api/v1/interface-state")

    assert response.status == falcon.HTTP_200, "A new browser should receive defaults."
    assert response.json == DEFAULT_STATE, "Missing state must use safe defaults."
    assert response.headers.get("set-cookie") is None, (
        "Reading default state must not issue a cookie."
    )


@pytest.mark.asyncio
async def test_post_sets_signed_messagepack_cookie_and_restores_state() -> None:
    """A validated update round-trips through the signed MessagePack cookie."""
    cookies = InterfaceStateCookies(SECRET)
    app = make_app(cookies)
    update = {"density": "comfortable", "presentation": "matrix"}
    async with testing.ASGIConductor(app) as conductor:
        response = await conductor.simulate_post(
            "/api/v1/interface-state",
            body=json.dumps(update),
            headers={"content-type": "application/json"},
        )
        set_cookie = response.headers.get("set-cookie")
        assert response.status == falcon.HTTP_200, "A valid update should succeed."
        assert response.json == update, "The response should echo validated controls."
        assert set_cookie is not None, "A valid update must issue one cookie."
        cookie = parse_cookie(set_cookie)
        assert cookie["httponly"] is True, "The preference cookie must be HttpOnly."
        assert cookie["samesite"] == "Lax", "The preference cookie must use Lax."
        assert cookie["path"] == "/", "The preference cookie must cover the app."
        assert cookie["max-age"] == "31536000", "The cookie must last one year."
        assert not cookie["secure"], "HTTP loopback cookies must remain usable."

        token = cookie.value
        payload = cookie_messagepack_payload(token)
        assert msgspec.msgpack.decode(payload) == update, (
            "The signed cookie payload must be the two-value MessagePack map."
        )
        with pytest.raises(msgspec.DecodeError):
            msgspec.json.decode(payload)

        restored = await conductor.simulate_get(
            "/api/v1/interface-state",
            headers={"cookie": f"{COOKIE_NAME}={token}"},
        )
        secure_response = await conductor.simulate_post(
            "/api/v1/interface-state",
            body=json.dumps(update),
            headers={"content-type": "application/json"},
            protocol="https",
        )

    assert restored.status == falcon.HTTP_200, "A valid cookie should restore state."
    assert restored.json == update, "Restored controls must match the saved values."
    assert restored.headers.get("set-cookie") is None, "GET must not rewrite state."
    assert parse_cookie(secure_response.headers["set-cookie"])["secure"] is True, (
        "HTTPS requests must set Secure."
    )


@pytest.mark.asyncio
async def test_missing_tampered_expired_and_invalid_cookies_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid signatures, ages and schemas are ignored without exposing errors."""
    cookies = InterfaceStateCookies(SECRET)
    valid = signed_token(
        cookies,
        {
            "density": "compact",
            "presentation": "list",
        },
    )
    tampered = tamper_signed_token(valid)
    invalid_schema = signed_token(
        cookies,
        {
            "density": "giant",
            "presentation": "panorama",
        },
    )
    invalid_shape = signed_token(cookies, ["compact", "list"])
    malformed_signed_payload = (
        cookies._serializer
        .make_signer()
        .sign(base64.urlsafe_b64encode(b"\xc1").rstrip(b"="))
        .decode("ascii")
    )

    monkeypatch.setattr(TimestampSigner, "get_timestamp", ancient_timestamp)
    expired = signed_token(
        cookies,
        {"density": "compact", "presentation": "list"},
    )
    monkeypatch.undo()

    async with testing.ASGIConductor(make_app(cookies)) as conductor:
        responses = [
            await conductor.simulate_get("/api/v1/interface-state"),
            *[
                await conductor.simulate_get(
                    "/api/v1/interface-state",
                    headers={"cookie": f"{COOKIE_NAME}={token}"},
                )
                for token in (
                    tampered,
                    expired,
                    invalid_schema,
                    invalid_shape,
                    malformed_signed_payload,
                )
            ],
        ]

    assert [response.json for response in responses] == [
        DEFAULT_STATE,
        DEFAULT_STATE,
        DEFAULT_STATE,
        DEFAULT_STATE,
        DEFAULT_STATE,
        DEFAULT_STATE,
    ], "Missing, tampered, expired and malformed cookies must fall back safely."


@pytest.mark.asyncio
async def test_invalid_and_oversized_updates_do_not_set_cookie() -> None:
    """Rejected request bodies cannot mutate browser state."""
    cookies = InterfaceStateCookies(SECRET)
    async with testing.ASGIConductor(make_app(cookies)) as conductor:
        invalid = await conductor.simulate_post(
            "/api/v1/interface-state",
            body='{"density":"giant","presentation":"panorama"}',
            headers={"content-type": "application/json"},
        )
        oversized = await conductor.simulate_post(
            "/api/v1/interface-state",
            body=" " * 1025,
            headers={"content-type": "application/json"},
        )
        unsupported_media = await conductor.simulate_post(
            "/api/v1/interface-state",
            body=json.dumps(DEFAULT_STATE),
            headers={"content-type": "text/plain"},
        )

    assert invalid.status == falcon.HTTP_400, "Invalid enum updates must be rejected."
    assert invalid.headers.get("set-cookie") is None, (
        "Invalid updates must not set a cookie."
    )
    assert oversized.status == falcon.HTTP_413, "Bodies over 1,024 bytes must fail."
    assert oversized.headers.get("set-cookie") is None, (
        "Oversized updates must not set a cookie."
    )
    assert unsupported_media.status == falcon.HTTP_415, (
        "Updates must use application/json."
    )
    assert unsupported_media.headers.get("set-cookie") is None, (
        "Unsupported media types must not set a cookie."
    )


def test_interface_state_validates_enums_and_defaults() -> None:
    """Direct construction applies the same enum contract as request decoding."""
    assert InterfaceState() == InterfaceState(
        density="overview",
        presentation="panorama",
    ), "Direct construction must use the documented defaults."
    with pytest.raises(ValueError, match=r"^$"):
        InterfaceState(density=typ.cast("typ.Literal['overview']", "giant"))


def test_signing_key_is_reused_private_and_race_safe(tmp_path: pathlib.Path) -> None:
    """Concurrent first reads converge on one persistent private signing key."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        keys = list(executor.map(load_signing_key, [tmp_path] * 8))

    key_path = tmp_path / SIGNING_KEY_FILENAME
    assert len(set(keys)) == 1, "Concurrent creation must converge on one key."
    assert len(keys[0]) == 32, "Signing keys must contain exactly 32 bytes."
    assert load_signing_key(tmp_path) == keys[0], "Subsequent calls must reuse the key."
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600, (
        "The persistent signing key must be private."
    )
