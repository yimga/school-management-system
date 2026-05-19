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
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

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

# v3.37.0 — legacy header family aliases for the 2026-05-19 → 2026-08-18
# dual-emit migration window. Receivers built against the original
# ``X-Migration-Cloud-*`` family stay supported until they migrate, via
# ``verify(..., accept_legacy=True)``. Default is ``True`` until 2026-08-18.
LEGACY_SIGNATURE_HEADER = "X-Migration-Cloud-Signature"
LEGACY_TIMESTAMP_HEADER = "X-Migration-Cloud-Timestamp"
LEGACY_EVENT_HEADER = "X-Migration-Cloud-Event"
LEGACY_VERSION_HEADER = "X-Migration-Cloud-Version"

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
    # hmac.compare_digest accepts equal-length bytes; encode both sides.
    # Non-ASCII material is not valid in the signature wire format, so
    # convert it into the same typed failure callers already handle for
    # mismatched digests.
    try:
        expected_bytes = expected.encode("ascii")
        header_bytes = header_str.encode("ascii")
    except UnicodeEncodeError as exc:
        raise BadSignatureError(
            "webhook verifier: signature contains non-ASCII bytes"
        ) from exc
    if not hmac.compare_digest(expected_bytes, header_bytes):
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

    .. deprecated:: 1.0.0-rc.1
        Use :func:`verify` instead — it accepts the full header mapping
        and transparently falls back across the canonical / legacy
        header families, returning a :class:`VerifyResult` with
        non-sensitive diagnostics. ``verify_signature`` continues to
        work but will be removed in 2.0. See ``MIGRATION_TO_1_0.md``.

    See :func:`verify_signature_strict` for argument documentation.
    """
    import warnings

    warnings.warn(
        "verify_signature() is deprecated as of 1.0.0-rc.1 and will be "
        "removed in 2.0; use verify(headers, body, secret) instead — it "
        "returns a VerifyResult and handles the legacy-header fallback.",
        DeprecationWarning,
        stacklevel=2,
    )
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


@dataclass(frozen=True)
class VerifyResult:
    """Result of :func:`verify` — boolean ``valid`` plus diagnostics.

    Attributes:
        valid: True iff the HMAC matched the body under the given secret.
        used_legacy_header_family: True iff the signature was read from
            the legacy ``X-Migration-Cloud-Signature`` header rather than
            the canonical ``X-RunMyCampus-Signature`` header. Subscribers
            should warn-log when this flips True so they know to migrate
            before the dual-emit window closes on 2026-08-18.
        signature_header_name: The header NAME the verifier consumed.
            Useful for log lines (e.g. "verified via X-RunMyCampus-Signature").
            NEVER contains secret/signature bytes.
        reason: Empty when ``valid`` is True; a short non-sensitive
            failure category otherwise (``"missing-header"``,
            ``"unsupported-algorithm"``, ``"bad-signature"``,
            ``"clock-skew"``, ``"legacy-rejected"``).
    """

    valid: bool
    used_legacy_header_family: bool = False
    signature_header_name: str = ""
    reason: str = ""


def _get_header_case_insensitive(
    headers: Mapping[str, Any], name: str,
) -> Optional[Any]:
    """Return the first matching header value across case variants.

    Accepts the canonical-case form (``X-RunMyCampus-Signature``), the
    common normalized forms, and arbitrary mixed-case plain mappings.
    """
    if headers is None:
        return None
    for candidate in (name, name.lower(), name.upper()):
        try:
            value = headers.get(candidate)  # type: ignore[union-attr]
        except AttributeError:
            return None
        if value is not None:
            return value
    target = name.lower()
    try:
        items = headers.items()
    except AttributeError:
        return None
    for key, value in items:
        if isinstance(key, str) and key.lower() == target and value is not None:
            return value
    return None


def verify(
    headers: Mapping[str, Any],
    body: _BytesLike,
    secret: _BytesLike,
    *,
    accept_legacy: bool = True,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> VerifyResult:
    """v3.37.0 — verify a delivery from EITHER header family.

    Preference order: the canonical ``X-RunMyCampus-Signature`` header is
    consulted first; the legacy ``X-Migration-Cloud-Signature`` is the
    fallback IFF ``accept_legacy=True`` (the default during the 2026-05-19
    → 2026-08-18 dual-emit window). After 2026-08-18 callers should flip
    ``accept_legacy=False`` to fail-closed on legacy-only deliveries.

    The returned :class:`VerifyResult` carries a
    ``used_legacy_header_family`` flag so subscriber middleware can
    warn-log without changing fail-closed posture.

    Constant-time compare uses :func:`hmac.compare_digest` (inherited
    from :func:`verify_signature_strict`). Failure ``reason`` strings are
    non-sensitive — safe to log.
    """
    new_value = _get_header_case_insensitive(headers, SIGNATURE_HEADER)
    legacy_value = _get_header_case_insensitive(headers, LEGACY_SIGNATURE_HEADER)
    new_timestamp = _get_header_case_insensitive(headers, TIMESTAMP_HEADER)
    legacy_timestamp = _get_header_case_insensitive(headers, LEGACY_TIMESTAMP_HEADER)

    # Preference order: prefer the new family when present.
    used_legacy = False
    new_header = _coerce_header(new_value)
    legacy_header = _coerce_header(legacy_value)
    if new_header:
        signature_value = new_value
        timestamp_value = new_timestamp
        header_name = SIGNATURE_HEADER
    elif legacy_header:
        if not accept_legacy:
            return VerifyResult(
                valid=False,
                used_legacy_header_family=True,
                signature_header_name=LEGACY_SIGNATURE_HEADER,
                reason="legacy-rejected",
            )
        signature_value = legacy_value
        timestamp_value = legacy_timestamp
        header_name = LEGACY_SIGNATURE_HEADER
        used_legacy = True
    else:
        return VerifyResult(
            valid=False,
            used_legacy_header_family=False,
            signature_header_name="",
            reason="missing-header",
        )

    try:
        verify_signature_strict(
            body,
            signature_value,
            secret,
            timestamp_header=timestamp_value,
            tolerance_seconds=tolerance_seconds,
            now=now,
        )
    except MissingHeaderError:
        return VerifyResult(
            valid=False,
            used_legacy_header_family=used_legacy,
            signature_header_name=header_name,
            reason="missing-header",
        )
    except UnsupportedAlgorithmError:
        return VerifyResult(
            valid=False,
            used_legacy_header_family=used_legacy,
            signature_header_name=header_name,
            reason="unsupported-algorithm",
        )
    except ClockSkewError:
        return VerifyResult(
            valid=False,
            used_legacy_header_family=used_legacy,
            signature_header_name=header_name,
            reason="clock-skew",
        )
    except BadSignatureError:
        return VerifyResult(
            valid=False,
            used_legacy_header_family=used_legacy,
            signature_header_name=header_name,
            reason="bad-signature",
        )
    return VerifyResult(
        valid=True,
        used_legacy_header_family=used_legacy,
        signature_header_name=header_name,
        reason="",
    )


__all__ = [
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "EVENT_HEADER",
    "VERSION_HEADER",
    "LEGACY_SIGNATURE_HEADER",
    "LEGACY_TIMESTAMP_HEADER",
    "LEGACY_EVENT_HEADER",
    "LEGACY_VERSION_HEADER",
    "SUPPORTED_PREFIX",
    "DEFAULT_TOLERANCE_SECONDS",
    "compute_signature",
    "verify_signature",
    "verify_signature_strict",
    "verify",
    "VerifyResult",
]
