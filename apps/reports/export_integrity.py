"""
Cryptographic integrity for downloadable exports (enterprise data trust).

Verification (offline): recompute SHA-256 of the response body, rebuild the signing
string, HMAC-SHA256 with Django SECRET_KEY (server-side). Consumers without the
secret cannot forge signatures; tenants verify via platform-published tooling or API.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNING_VERSION = "v1"


def content_sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_export_signing_message(
    *,
    export_key: str,
    school_id: str,
    content_sha256_hex_val: str,
) -> bytes:
    raw = f"{SIGNING_VERSION}|{export_key}|{school_id}|{content_sha256_hex_val}"
    return raw.encode("utf-8")


def sign_export_content(
    content: bytes,
    *,
    export_key: str,
    school_id: str,
    secret: str,
) -> tuple[str, str, str]:
    """
    Returns (content_sha256_hex, signature_hex, signing_version).
    """
    sha = content_sha256_hex(content)
    msg = build_export_signing_message(
        export_key=export_key,
        school_id=str(school_id),
        content_sha256_hex_val=sha,
    )
    sig = hmac.new(
        secret.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).hexdigest()
    return sha, sig, SIGNING_VERSION


def verify_export_signature(
    content: bytes,
    *,
    export_key: str,
    school_id: str,
    secret: str,
    signature_hex: str,
) -> bool:
    """Constant-time verify signature hex matches recomputed HMAC."""
    sha = content_sha256_hex(content)
    msg = build_export_signing_message(
        export_key=export_key,
        school_id=str(school_id),
        content_sha256_hex_val=sha,
    )
    expected = hmac.new(
        secret.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected.strip().lower(), (signature_hex or "").strip().lower())


def attach_export_integrity_headers(
    response,
    *,
    content: bytes,
    export_key: str,
    school_id: str,
    secret: str,
) -> None:
    sha, sig, ver = sign_export_content(
        content,
        export_key=export_key,
        school_id=str(school_id),
        secret=secret,
    )
    response["X-Export-Content-SHA256"] = sha
    response["X-Export-Signature"] = f"{ver}={sig}"
    response["X-Export-Integrity-Algorithm"] = "HMAC-SHA256"
