"""Per-integration webhook signature-scheme dispatch for the LIVE inbound rail.

The live payment webhook (``apps/finance/views_payments.py::payment_provider_webhook``)
has historically verified EVERY provider with one generic HMAC-SHA256 over the raw
body (``WebhookSecurityValidator.validate_signature``). That is exactly how the
MoMo aggregators the platform launched with sign their callbacks — but it is NOT
how Stripe, Paystack, Flutterwave, or M-Pesa Daraja actually sign theirs. So an
Integration pointed at one of those PSPs could not have its callback signatures
verified the way the PSP intends.

This module lets an Integration opt into a provider-accurate verifier by setting
``config["signature_scheme"]``. The contract is deliberately additive:

* key ABSENT (every Integration shipped to date) -> the caller keeps the exact
  generic HMAC path, so live behaviour is unchanged until an operator opts in;
* ``"generic_hmac"`` -> same generic path, stated explicitly;
* a recognised scheme -> the matching provider-accurate verifier;
* a set-but-UNKNOWN scheme -> fail closed. A misconfiguration must never silently
  downgrade to a weaker check.

The cryptography lives in :mod:`apps.finance.webhooks.signature_verifiers` (pure,
stdlib, constant-time, already unit-tested). This module only maps a scheme name +
Integration ``config`` to the right verifier call — no Django, no models, no I/O —
so it is safe to import from the request path and trivial to unit-test.
"""

from __future__ import annotations

from typing import Any

from apps.finance.webhooks import signature_verifiers as sv

# Sentinel meaning "use the historical generic HMAC path". The caller owns that
# path; this module is only consulted for a genuinely non-generic scheme.
GENERIC_SCHEME = "generic_hmac"

# Scheme names an Integration may set in ``config["signature_scheme"]`` to opt into
# provider-accurate verification.
PROVIDER_ACCURATE_SCHEMES = frozenset(
    {"stripe", "paystack", "flutterwave", "mpesa_daraja", "aggregator_hmac"}
)


def scheme_from_config(config: dict[str, Any] | None) -> str:
    """Return the normalized non-generic scheme for an Integration.

    Returns ``""`` when the key is absent or set to the generic sentinel — the
    signal to the caller to keep the historical generic HMAC path unchanged.
    """
    raw = (config or {}).get("signature_scheme")
    scheme = str(raw or "").strip().lower()
    if not scheme or scheme == GENERIC_SCHEME:
        return ""
    return scheme


def is_recognized_scheme(scheme: str | None) -> bool:
    """True if ``scheme`` is safe to store in ``config["signature_scheme"]``.

    Accepts the empty/absent value and the explicit ``generic_hmac`` sentinel
    (both mean "keep the historical generic HMAC path") plus every
    provider-accurate scheme. An unrecognised name is REJECTED so a typo (e.g.
    ``"strpe"``) is caught when an operator CONFIGURES the integration — not
    later, as a silent stream of fail-closed 403s once the PSP goes live. This is
    the write-time twin of the request-time fail-closed in
    :func:`verify_provider_signature`.
    """
    normalized = str(scheme or "").strip().lower()
    if not normalized or normalized == GENERIC_SCHEME:
        return True
    return normalized in PROVIDER_ACCURATE_SCHEMES


def verify_provider_signature(
    scheme: str,
    *,
    headers: dict[str, Any] | None,
    raw_body: bytes,
    secret: str,
    config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Verify a webhook signature with the provider-accurate verifier for ``scheme``.

    Only meaningful for a non-generic scheme (see :func:`scheme_from_config`).
    Returns ``(verified, reason)``; an unrecognised scheme fails closed with
    ``(False, "unknown_signature_scheme")``. ``reason`` is a fixed machine token
    from the verifier layer — never secret material.
    """
    config = config or {}
    scheme = (scheme or "").strip().lower()
    tolerance = int(config.get("timestamp_tolerance_seconds", 300) or 300)

    if scheme == "stripe":
        return sv.verify_stripe(headers, raw_body, secret, tolerance_seconds=tolerance)

    if scheme == "paystack":
        return sv.verify_paystack(headers, raw_body, secret)

    if scheme == "flutterwave":
        # Flutterwave compares a shared secret HASH sent in the ``verif-hash``
        # header; it may be stored separately from the HMAC ``webhook_secret``.
        secret_hash = (
            config.get("flutterwave_secret_hash")
            or config.get("secret_hash")
            or secret
        )
        return sv.verify_flutterwave(headers, raw_body, secret_hash)

    if scheme == "mpesa_daraja":
        return sv.verify_mpesa_daraja(
            headers,
            raw_body,
            secret,
            header_name=config.get("signature_header", "X-Signature"),
        )

    if scheme == "aggregator_hmac":
        return sv.verify_aggregator_hmac(
            headers,
            raw_body,
            secret,
            header_name=config.get("signature_header", "X-Signature"),
            algorithm=str(config.get("signature_algorithm", "sha256")),
            timestamp_header=config.get("timestamp_header") or None,
            tolerance_seconds=tolerance,
            body_template=config.get("signature_body_template", "{body}"),
        )

    return False, "unknown_signature_scheme"


__all__ = [
    "GENERIC_SCHEME",
    "PROVIDER_ACCURATE_SCHEMES",
    "is_recognized_scheme",
    "scheme_from_config",
    "verify_provider_signature",
]
