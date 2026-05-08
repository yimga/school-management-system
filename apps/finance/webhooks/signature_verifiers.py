"""Per-provider non-charging webhook signature verification.

Stdlib only. No Django or model imports. Pure functions returning
(verified: bool, reason: str). Constant-time comparisons throughout.
Never logs raw header values, secrets, or bodies.

Each verifier follows the provider's documented signing scheme:

- Stripe: HMAC-SHA256 of "{timestamp}.{body}"; header "Stripe-Signature"
  (parts t=, v1=); ≤ tolerance seconds skew.
- Paystack: HMAC-SHA512 of body; header "x-paystack-signature".
- Flutterwave: constant-time compare of header "verif-hash" to FLW_SECRET_HASH.
- MTN MoMo / Orange Money: aggregator-dependent. We support a generic
  "{algo} HMAC of body, optional t= timestamp" mode driven by an explicit
  config dict so the call site stays identical across aggregators.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def _h(headers: dict[str, Any] | None, name: str) -> str:
    """Case-insensitive header lookup. Returns empty string when absent."""
    if not headers:
        return ""
    target = name.strip().lower()
    for k, v in headers.items():
        if str(k).strip().lower() == target:
            return str(v or "")
    return ""


def _const_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_stripe(
    headers: dict[str, Any] | None,
    raw_body: bytes,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> tuple[bool, str]:
    """Stripe webhook verification per https://stripe.com/docs/webhooks/signatures.

    Header "Stripe-Signature" carries comma-separated parts: t=<unix>, v1=<hex>.
    Signed payload = "{t}.{body}", HMAC-SHA256 with the webhook secret.
    """
    if not secret:
        return False, "stripe_secret_missing"
    sig = _h(headers, "Stripe-Signature")
    if not sig:
        return False, "stripe_signature_header_missing"
    parts: dict[str, str] = {}
    for chunk in sig.split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()
    ts = parts.get("t") or ""
    v1 = parts.get("v1") or ""
    if not ts or not v1:
        return False, "stripe_signature_malformed"
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return False, "stripe_timestamp_invalid"
    cur = float(now if now is not None else time.time())
    if abs(cur - ts_int) > int(tolerance_seconds or 0):
        return False, "stripe_timestamp_outside_tolerance"
    signed = f"{ts}.".encode("utf-8") + (raw_body or b"")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not _const_time_eq(v1.lower(), expected.lower()):
        return False, "stripe_signature_mismatch"
    return True, ""


def verify_paystack(
    headers: dict[str, Any] | None,
    raw_body: bytes,
    secret: str,
) -> tuple[bool, str]:
    """Paystack: header "x-paystack-signature" = HMAC-SHA512(body) hex with secret key."""
    if not secret:
        return False, "paystack_secret_missing"
    sig = _h(headers, "x-paystack-signature")
    if not sig:
        return False, "paystack_signature_header_missing"
    expected = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha512).hexdigest()
    if not _const_time_eq(sig.strip().lower(), expected.lower()):
        return False, "paystack_signature_mismatch"
    return True, ""


def verify_flutterwave(
    headers: dict[str, Any] | None,
    raw_body: bytes,
    secret_hash: str,
) -> tuple[bool, str]:
    """Flutterwave: header "verif-hash" must equal the FLW_SECRET_HASH set in dashboard.

    Body is not signed; the provider relies on the shared secret in the header
    plus HTTPS. We still constant-time compare to avoid timing leaks.
    """
    del raw_body  # unused — Flutterwave does not sign the body.
    if not secret_hash:
        return False, "flutterwave_secret_hash_missing"
    sig = _h(headers, "verif-hash")
    if not sig:
        return False, "flutterwave_verif_hash_header_missing"
    if not _const_time_eq(sig.strip(), secret_hash.strip()):
        return False, "flutterwave_verif_hash_mismatch"
    return True, ""


def verify_aggregator_hmac(
    headers: dict[str, Any] | None,
    raw_body: bytes,
    secret: str,
    *,
    header_name: str,
    algorithm: str = "sha256",
    timestamp_header: str | None = None,
    tolerance_seconds: int = 300,
    body_template: str = "{body}",
    now: float | None = None,
) -> tuple[bool, str]:
    """Generic HMAC verifier for MoMo / Orange aggregators (Hub2, MFS Africa, Yas, etc.).

    Most aggregators sign either {body} or {timestamp}.{body} with HMAC-{algo}.
    Aggregator config (stored in Integration.config) selects the variant.
    """
    if not secret:
        return False, "aggregator_secret_missing"
    if not header_name:
        return False, "aggregator_header_name_missing"
    sig = _h(headers, header_name)
    if not sig:
        return False, "aggregator_signature_header_missing"
    algo_impl = getattr(hashlib, algorithm.strip().lower(), None)
    if algo_impl is None:
        return False, f"aggregator_unsupported_algorithm:{algorithm}"
    ts = ""
    if timestamp_header:
        ts = _h(headers, timestamp_header)
        if not ts:
            return False, "aggregator_timestamp_header_missing"
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            return False, "aggregator_timestamp_invalid"
        cur = float(now if now is not None else time.time())
        if abs(cur - ts_int) > int(tolerance_seconds or 0):
            return False, "aggregator_timestamp_outside_tolerance"
    body_str = (raw_body or b"").decode("utf-8", errors="replace")
    signed = body_template.format(body=body_str, timestamp=ts).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed, algo_impl).hexdigest()
    candidate = sig.strip()
    if "=" in candidate:
        # Some aggregators prefix with "v1=" or "{algo}=".
        _, candidate = candidate.split("=", 1)
        candidate = candidate.strip()
    if not _const_time_eq(candidate.lower(), expected.lower()):
        return False, "aggregator_signature_mismatch"
    return True, ""


# Stable export surface for the gateway/processor call sites.
__all__ = [
    "verify_stripe",
    "verify_paystack",
    "verify_flutterwave",
    "verify_aggregator_hmac",
]
