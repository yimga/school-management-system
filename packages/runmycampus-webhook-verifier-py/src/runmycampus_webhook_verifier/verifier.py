"""HMAC-SHA256 webhook signature verifier.

Pure stdlib (``hmac`` + ``hashlib`` + ``time``); no third-party deps.

Header contract
---------------

The platform writes the following headers on every outbound delivery:

* ``X-RunMyCampus-Signature`` — ``sha256=<lowercase-hex-digest>``
* ``X-RunMyCampus-Timestamp`` — Unix seconds as integer string
* ``X-RunMyCampus-Event`` — dotted event class (``migration.bundle.completed``)
* ``X-RunMyCampus-Version`` — signature format version (``v1`` today)

The verifier accepts the raw request body bytes the platform signed
PLUS the headers, computes the expected HMAC under the customer's
secret, and compares in constant time.

Two API styles
--------------

* :func:`verify_signature` — boolean return, swallows all errors.
  Suitable for "fail-closed-on-any-error" middlewares.
* :func:`verify_signature_strict` — raises a typed
  :class:`~runmycampus_webhook_verifier.exceptions.VerificationError`
  subclass so the caller can log *why* (without leaking the secret).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional, Union

from .exceptions import (
    BadSignatureError,
    ClockSkewError,
    MissingHeaderError,
    UnsupportedAlgorithmError,
    VerificationError,
)


# Public header names the platform writes; do not hard-code in caller code.
SIGNATURE_HEADER = "X-RunMyCampus-Signature"
TIMESTAMP_HEADER = "X-RunMyCampus-Timestamp"
EVENT_HEADER = "X-RunMyCampus-Event"
VERSION_HEADER = "X-RunMyCampus-Version"

# Signature prefix that identifies the digest algorithm. Currently only
# ``sha256`` is emitted; the prefix is checked so a future ``sha512=``
# rollout fails closed in old verifiers (rather than silently passing
# whatever a malicious sender supplies).
SUPPORTED_PREFIX = "sha256="

# Default clock-skew tolerance — matches Stripe / GitHub / Twilio.
DEFAULT_TOLERANCE_SECONDS = 300


_BytesLike = Union[str, bytes, bytearray, memoryview]


def _coerce_bytes(value: _BytesLike) -> bytes:
    """Normalize ``str | bytes | bytearray | memoryview`` to ``bytes``."""
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    return value


def compute_signature(
    body: _BytesLike,
    secret: _BytesLike,
) -> str:
    """Return ``sha256=<hex>`` for the given raw body + secret.

    Useful for unit tests, replay tooling, and debugging signature
    mismatches. Do NOT use the output to compare against a header with
    ``==``; use :func:`verify_signature` so the compare runs in constant
    time.
    """
    body_bytes = _coerce_bytes(body)
    secret_bytes = _coerce_bytes(secret)
    digest = hmac.new(secret_bytes, body_bytes, hashlib.sha256).hexdigest()
    return SUPPORTED_PREFIX + digest


def _coerce_header(value) -> Optional[str]:
    """Normalize a header value to ``str`` (or ``None`` if absent / undecodable)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
    # Tolerate list-of-strings (some frameworks return that for
    # repeated headers). Take the first.
    if isinstance(value, (list, tuple)) and value:
        return _coerce_header(value[0])
    return None


def verify_signature_strict(
    body: _BytesLike,
    signature_header: Union[str, bytes, None],
    secret: _BytesLike,
    *,
    timestamp_header: Union[str, bytes, None] = None,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> None:
    """Raise on any verification failure; return ``None`` on success.

    Arguments:
        body: The raw request body bytes. MUST be the exact bytes the
            platform signed — do NOT re-serialize the JSON or change
            key ordering before passing here.
        signature_header: The value of the ``X-RunMyCampus-Signature``
            header.
        secret: Shared HMAC secret the platform gave you at subscription
            creation time. Treat as opaque material.
        timestamp_header: Value of ``X-RunMyCampus-Timestamp``. When
            present, the absolute skew vs ``now`` MUST be within
            ``tolerance_seconds`` or :class:`ClockSkewError` is raised.
            When ``None``, the clock-skew check is skipped — callers
            that need replay defense should always pass this.
        tolerance_seconds: Max accepted skew in seconds. Default 300.
        now: Current unix-time in seconds (float). Defaults to
            ``time.time()``. Pass an explicit value in tests.

    Raises:
        MissingHeaderError: signature header missing / empty.
        UnsupportedAlgorithmError: prefix is not ``sha256=``.
        BadSignatureError: digest mismatch (tamper / wrong secret /
            non-canonical body bytes).
        ClockSkewError: timestamp outside tolerance.

    Security notes:
        Constant-time compare uses :func:`hmac.compare_digest`. We
        intentionally do not echo the bad header value or skew amount
        beyond the magnitude — all error messages are safe to log.
    """
    header_str = _coerce_header(signature_header)
    if not header_str:
        raise MissingHeaderError(
            f"webhook verifier: missing or empty {SIGNATURE_HEADER!r} header"
        )
    if not header_str.startswith(SUPPORTED_PREFIX):
        raise UnsupportedAlgorithmError(
            "webhook verifier: signature algorithm not supported by this "
            "SDK version (only 'sha256=' is accepted); upgrade the verifier "
            "package to a release that supports the new prefix."
        )
    expected = compute_signature(body, secret)
    # hmac.compare_digest accepts equal-length bytes; encode both sides
    # so a unicode-encoded header still compares.
    if not hmac.compare_digest(
        expected.encode("ascii"), header_str.encode("ascii")
    ):
        raise BadSignatureError(
            "webhook verifier: signature did not match HMAC of the body "
            "under the given secret (body tampered, wrong secret, or "
            "body bytes are not the canonical bytes the platform signed)"
        )

    # Clock-skew check is opt-in: only enforced when caller supplied the
    # timestamp header. Customers without replay defense set up should
    # pass it — but a missing timestamp does NOT fail verification (the
    # platform may not always send it for legacy subscriptions).
    if timestamp_header is None:
        return None
    ts_str = _coerce_header(timestamp_header)
    if not ts_str:
        # If caller passed something but it decoded to empty, treat
        # exactly like a missing-header — fail closed.
        raise MissingHeaderError(
            f"webhook verifier: {TIMESTAMP_HEADER!r} present but empty"
        )
    try:
        signed_at = float(ts_str)
    except ValueError as exc:
        raise MissingHeaderError(
            f"webhook verifier: {TIMESTAMP_HEADER!r} is not a numeric "
            "unix-seconds value"
        ) from exc
    current = float(now if now is not None else time.time())
    skew = abs(current - signed_at)
    if skew > float(tolerance_seconds):
        raise ClockSkewError(
            f"webhook verifier: signed timestamp is outside the "
            f"{tolerance_seconds}-second tolerance window",
            skew_seconds=skew,
        )
    return None


def verify_signature(
    body: _BytesLike,
    signature_header: Union[str, bytes, None],
    secret: _BytesLike,
    *,
    timestamp_header: Union[str, bytes, None] = None,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Return ``True`` iff every check passes; ``False`` on any failure.

    This is the lenient wrapper around :func:`verify_signature_strict` —
    use this in middlewares that want to fail closed without dispatching
    on the failure mode.

    See :func:`verify_signature_strict` for argument documentation.
    """
    try:
        verify_signature_strict(
            body,
            signature_header,
            secret,
            timestamp_header=timestamp_header,
            tolerance_seconds=tolerance_seconds,
            now=now,
        )
        return True
    except VerificationError:
        return False


__all__ = [
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "EVENT_HEADER",
    "VERSION_HEADER",
    "SUPPORTED_PREFIX",
    "DEFAULT_TOLERANCE_SECONDS",
    "compute_signature",
    "verify_signature",
    "verify_signature_strict",
]
