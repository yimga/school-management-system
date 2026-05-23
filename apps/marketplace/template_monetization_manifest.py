"""Wave E scaffold — ExperienceTemplate monetization manifest schema.

Declares the SHAPE that monetization metadata MUST satisfy when Wave E+
counsel signoff + Stripe settlement infrastructure are unblocked. The
publishing surface is gated behind ``RMC_TEMPLATE_MONETIZATION_ENABLED``
(default False; counsel-pending).

See docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md for the gates that
must clear before the gate flips.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PRICING_MODELS = {"free", "one-time", "subscription-monthly", "subscription-annual"}
SETTLEMENT_PROVIDERS = {"stripe", "flutterwave", "mpesa", "manual-bank-transfer"}
ALLOWED_CURRENCIES = {
    "USD", "EUR", "GBP", "NGN", "KES", "ZAR", "GHS", "XAF", "XOF",
    "INR", "PKR", "BDT", "JPY", "KRW", "CNY", "PHP", "MYR", "IDR",
    "AUD", "AED", "MAD", "MXN", "BRL",
}


@dataclass(frozen=True)
class MonetizationValidationResult:
    ok: bool
    findings: tuple[str, ...]
    pricing_model: str
    settlement_provider: str
    rev_share_pct: float


def validate_monetization_manifest(manifest: dict[str, Any]) -> MonetizationValidationResult:
    """Validate a template monetization manifest fragment.

    Embedded inside a partner manifest under the optional ``monetization``
    key. When ``RMC_TEMPLATE_MONETIZATION_ENABLED`` is unset (the default), the
    publishing surface ignores monetization manifests entirely and treats every
    template as ``pricing_model=free``.
    """
    findings: list[str] = []
    if not isinstance(manifest, dict):
        return MonetizationValidationResult(
            ok=False,
            findings=("monetization manifest must be a JSON object",),
            pricing_model="",
            settlement_provider="",
            rev_share_pct=0.0,
        )

    pricing_model = str(manifest.get("pricing_model") or "").strip()
    if not pricing_model:
        findings.append("pricing_model is required")
    elif pricing_model not in PRICING_MODELS:
        findings.append(
            f"pricing_model '{pricing_model}' not in approved set {sorted(PRICING_MODELS)}"
        )

    if pricing_model != "free":
        amount = manifest.get("amount_minor_units")
        if not isinstance(amount, int) or amount <= 0:
            findings.append("amount_minor_units must be positive int (cents/paise/etc) for paid pricing")
        currency = str(manifest.get("currency") or "").strip().upper()
        if currency not in ALLOWED_CURRENCIES:
            findings.append(f"currency '{currency}' not in approved set")
        provider = str(manifest.get("settlement_provider") or "").strip()
        if provider not in SETTLEMENT_PROVIDERS:
            findings.append(
                f"settlement_provider '{provider}' not in approved set {sorted(SETTLEMENT_PROVIDERS)}"
            )
        rev_share_pct = manifest.get("rev_share_pct")
        if not isinstance(rev_share_pct, (int, float)) or not (0 <= rev_share_pct <= 100):
            findings.append("rev_share_pct must be a number in [0, 100]")

    counsel_attestation_id = str(manifest.get("counsel_attestation_id") or "").strip()
    if pricing_model != "free" and not counsel_attestation_id:
        findings.append(
            "counsel_attestation_id is required for any paid template — counsel signoff PDF "
            "must be filed before publish"
        )

    return MonetizationValidationResult(
        ok=len(findings) == 0,
        findings=tuple(findings),
        pricing_model=pricing_model,
        settlement_provider=str(manifest.get("settlement_provider") or ""),
        rev_share_pct=float(manifest.get("rev_share_pct") or 0.0),
    )


def example_monetization_manifest() -> dict[str, Any]:
    """Return a worked-example monetization manifest fragment."""
    return {
        "pricing_model": "one-time",
        "amount_minor_units": 9900,
        "currency": "USD",
        "settlement_provider": "stripe",
        "rev_share_pct": 70.0,
        "counsel_attestation_id": "ATTEST-2026-XX-PARTNER-PLACEHOLDER",
    }
