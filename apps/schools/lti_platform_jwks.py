"""LTI 1.3 platform JWKS infrastructure (Wave 25 v4.00.92, H10).

This module owns the **platform-side** RSA keypair that RunMyCampus uses to
sign LTI 1.3 access tokens (issued by ``lti_tool_token.py``) and any other
platform-signed JWTs that an LTI tool will need to verify against our public
JWKS endpoint.

Surface:

- :func:`get_or_generate_platform_keypair` -> ``(private_pem, public_pem)``.
  Persistent storage is via env vars ``RMC_LTI_PLATFORM_PRIVATE_KEY_PEM`` +
  ``RMC_LTI_PLATFORM_PUBLIC_KEY_PEM``. If unset, an *ephemeral* 2048-bit RSA
  keypair is generated in-process (dev only — the kid changes every restart).
- :func:`build_jwks` -> ``{"keys": [...]}`` JWKS document. ``kid`` is the
  first 16 hex characters of ``sha256(public_key_DER_bytes)``.
- :func:`sign_platform_jwt` -> compact JWS (RS256) with the ``kid`` header
  populated so the verifying tool can pick our key out of the JWKS array.
- :func:`current_kid` -> the active ``kid`` (handy for diagnostics + the
  H8 token endpoint).

Error taxonomy (8 states):
``ok`` / ``cryptography_missing`` / ``no_keys`` / ``bad_pem`` /
``serialize_error`` / ``sign_error`` / ``no_kid`` / ``unknown``.

NEVER logs raw private-key bytes. NEVER returns the private key from the
public-facing JWKS view.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import logging
import os
import time
from typing import Any

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


_PLATFORM_JWKS_ERROR_STATES: tuple[str, ...] = (
    "ok",
    "cryptography_missing",
    "no_keys",
    "bad_pem",
    "serialize_error",
    "sign_error",
    "no_kid",
    "unknown",
)


class PlatformJWKSError(Exception):
    """Raised when JWKS / sign helpers fail. ``reason`` is one of the
    8 :data:`_PLATFORM_JWKS_ERROR_STATES`."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason if reason in _PLATFORM_JWKS_ERROR_STATES else "unknown"


# Cached ephemeral keypair across the lifetime of the worker process so
# `kid` stays stable for the request. Persistent operators MUST set the
# env vars to avoid the value changing across restarts.
_EPHEMERAL_KEYPAIR_CACHE: dict[str, bytes] = {}


def _load_cryptography() -> tuple[Any, Any, Any, Any] | None:
    """Lazy-import :mod:`cryptography`. Returns ``None`` if missing so the
    smoke harness can SKIP without crashing dev environments."""
    try:
        rsa_mod = importlib.import_module("cryptography.hazmat.primitives.asymmetric.rsa")
        serialization = importlib.import_module(
            "cryptography.hazmat.primitives.serialization"
        )
        hashes = importlib.import_module("cryptography.hazmat.primitives.hashes")
        padding = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.padding"
        )
    except ImportError:
        return None
    return rsa_mod, serialization, hashes, padding


def _env_pem(name: str) -> bytes:
    """Read a PEM blob from the environment, stripping CRLF noise.

    Persistent operator configuration. Newlines may be encoded as ``\\n``
    when set via a single-line env var; we accept both.
    """
    raw = os.environ.get(name, "")
    if not raw:
        # Also check Django settings (for test harnesses that monkeypatch
        # settings instead of touching environ).
        raw = str(getattr(settings, name, "") or "")
    if not raw:
        return b""
    raw = raw.replace("\\n", "\n").strip()
    return raw.encode("utf-8")


def _generate_ephemeral_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh 2048-bit RSA keypair (dev only)."""
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    rsa_mod, serialization, _hashes, _padding = mods
    private = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def get_or_generate_platform_keypair() -> tuple[bytes, bytes]:
    """Return ``(private_pem, public_pem)``.

    Persistent storage: env vars ``RMC_LTI_PLATFORM_PRIVATE_KEY_PEM`` +
    ``RMC_LTI_PLATFORM_PUBLIC_KEY_PEM``. If unset, an ephemeral keypair is
    generated and cached for the lifetime of the process so the ``kid`` stays
    stable between requests within a single worker.
    """
    priv = _env_pem("RMC_LTI_PLATFORM_PRIVATE_KEY_PEM")
    pub = _env_pem("RMC_LTI_PLATFORM_PUBLIC_KEY_PEM")
    if priv and pub:
        return priv, pub

    cached_priv = _EPHEMERAL_KEYPAIR_CACHE.get("private_pem")
    cached_pub = _EPHEMERAL_KEYPAIR_CACHE.get("public_pem")
    if cached_priv and cached_pub:
        return cached_priv, cached_pub

    new_priv, new_pub = _generate_ephemeral_keypair()
    _EPHEMERAL_KEYPAIR_CACHE["private_pem"] = new_priv
    _EPHEMERAL_KEYPAIR_CACHE["public_pem"] = new_pub
    logger.info("LTI platform keypair generated (ephemeral, in-process only)")
    return new_priv, new_pub


def _b64url_uint(value: int) -> str:
    """JWA RFC-7518 base64url unsigned-int encoding."""
    if value == 0:
        return "AA"
    n = value
    octets = []
    while n > 0:
        octets.append(n & 0xFF)
        n >>= 8
    octets.reverse()
    return base64.urlsafe_b64encode(bytes(octets)).rstrip(b"=").decode("ascii")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _public_key_object(public_pem: bytes):
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    _rsa, serialization, _hashes, _padding = mods
    try:
        return serialization.load_pem_public_key(public_pem)
    except (ValueError, TypeError) as exc:
        raise PlatformJWKSError("bad_pem", "failed to parse public PEM") from exc


def _private_key_object(private_pem: bytes):
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    _rsa, serialization, _hashes, _padding = mods
    try:
        return serialization.load_pem_private_key(private_pem, password=None)
    except (ValueError, TypeError) as exc:
        raise PlatformJWKSError("bad_pem", "failed to parse private PEM") from exc


def _public_key_der(public_pem: bytes) -> bytes:
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    _rsa, serialization, _hashes, _padding = mods
    pub_obj = _public_key_object(public_pem)
    try:
        return pub_obj.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except (ValueError, TypeError) as exc:
        raise PlatformJWKSError("serialize_error", "DER serialize failed") from exc


def _kid_from_public_pem(public_pem: bytes) -> str:
    der = _public_key_der(public_pem)
    return hashlib.sha256(der).hexdigest()[:16]


def current_kid() -> str:
    """Return the current platform ``kid`` (SHA-256[:16] of public DER)."""
    _priv, pub = get_or_generate_platform_keypair()
    if not pub:
        raise PlatformJWKSError("no_keys", "no public key available")
    return _kid_from_public_pem(pub)


def build_jwks() -> dict[str, Any]:
    """Return JWKS JSON document for the LTI tool ecosystem.

    Shape:
    ``{"keys": [{"kty": "RSA", "kid": <hex>, "use": "sig", "alg": "RS256",
                  "n": <b64url>, "e": <b64url>}]}``.
    """
    _priv, pub = get_or_generate_platform_keypair()
    if not pub:
        raise PlatformJWKSError("no_keys", "no public key available")
    pub_obj = _public_key_object(pub)
    public_numbers = pub_obj.public_numbers()
    n_b64 = _b64url_uint(public_numbers.n)
    e_b64 = _b64url_uint(public_numbers.e)
    kid = _kid_from_public_pem(pub)
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": n_b64,
                "e": e_b64,
            }
        ]
    }


def sign_platform_jwt(
    *, claims: dict[str, Any], expires_in_seconds: int = 3600
) -> str:
    """Sign ``claims`` as a compact RS256 JWS with ``kid`` set on the header.

    Adds standard ``iat`` + ``exp`` if not already present. Does NOT log
    raw private-key bytes or the produced signature (only the kid is
    diagnostic-safe).
    """
    if not isinstance(claims, dict):
        raise PlatformJWKSError("unknown", "claims must be a dict")
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    _rsa, _serialization, hashes, padding = mods
    priv_pem, pub_pem = get_or_generate_platform_keypair()
    priv_obj = _private_key_object(priv_pem)
    kid = _kid_from_public_pem(pub_pem)
    if not kid:
        raise PlatformJWKSError("no_kid", "kid unavailable")

    now = int(time.time())
    body: dict[str, Any] = dict(claims)
    body.setdefault("iat", now)
    body.setdefault("exp", now + max(60, int(expires_in_seconds)))

    header = {"alg": "RS256", "typ": "JWT", "kid": kid}
    try:
        header_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        body_b64 = _b64url(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise PlatformJWKSError("serialize_error", "failed to serialize JWT body") from exc

    signing_input = f"{header_b64}.{body_b64}".encode("ascii")
    try:
        signature = priv_obj.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (ValueError, TypeError) as exc:
        raise PlatformJWKSError("sign_error", "RS256 sign failed") from exc

    return f"{header_b64}.{body_b64}.{_b64url(signature)}"


def decode_and_verify_platform_jwt(token: str) -> dict[str, Any]:
    """Decode + verify a JWT issued by :func:`sign_platform_jwt`.

    Returns the claims dict on success. Raises :class:`PlatformJWKSError`
    on signature failure or expired ``exp``.
    """
    mods = _load_cryptography()
    if mods is None:
        raise PlatformJWKSError("cryptography_missing", "cryptography not installed")
    _rsa, _serialization, hashes, padding = mods
    _priv_pem, pub_pem = get_or_generate_platform_keypair()
    pub_obj = _public_key_object(pub_pem)

    parts = (token or "").split(".")
    if len(parts) != 3:
        raise PlatformJWKSError("bad_pem", "malformed JWT")
    header_b64, body_b64, sig_b64 = parts

    def _pad(s: str) -> bytes:
        return (s + "=" * (-len(s) % 4)).encode("ascii")

    try:
        signature = base64.urlsafe_b64decode(_pad(sig_b64))
    except (ValueError, TypeError) as exc:
        raise PlatformJWKSError("bad_pem", "bad signature encoding") from exc
    signing_input = f"{header_b64}.{body_b64}".encode("ascii")
    try:
        pub_obj.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:  # invalid signature
        raise PlatformJWKSError("sign_error", "signature verification failed") from exc

    try:
        body = json.loads(base64.urlsafe_b64decode(_pad(body_b64)).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise PlatformJWKSError("serialize_error", "bad JWT body") from exc

    if not isinstance(body, dict):
        raise PlatformJWKSError("serialize_error", "JWT body must be a JSON object")
    exp = int(body.get("exp", 0) or 0)
    if exp and int(time.time()) > exp:
        raise PlatformJWKSError("sign_error", "expired_token")
    return body


@require_GET
def lti_platform_jwks_view(request) -> HttpResponse:
    """GET ``/.well-known/jwks.json`` (and ``/lti/jwks/`` alias).

    Anonymous-readable per LTI 1.3 spec — external tools must be able to
    fetch the platform's public keys without authenticating.

    # rbac-allow: lti-jwks-anonymous-public-key-distribution
    """
    try:
        body = build_jwks()
    except PlatformJWKSError as err:
        logger.warning("lti_platform_jwks_view error reason=%s", err.reason)
        return JsonResponse({"error": "jwks_unavailable", "reason": err.reason}, status=503)
    response = JsonResponse(body)
    response["Cache-Control"] = "public, max-age=3600"
    response["X-RMC-LTI-Kid"] = body.get("keys", [{}])[0].get("kid", "")
    return response


__all__ = [
    "PlatformJWKSError",
    "build_jwks",
    "current_kid",
    "decode_and_verify_platform_jwt",
    "get_or_generate_platform_keypair",
    "lti_platform_jwks_view",
    "sign_platform_jwt",
]
