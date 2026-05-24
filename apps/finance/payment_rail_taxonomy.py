"""
Canonical payment rail taxonomy (SFDP Phase 3 — batch 1453).

Maps profile rail enums, PaymentRail.RailKind, and PSP adapter capabilities.
"""

from __future__ import annotations

from typing import Any

# Profile / corridor rail codes (uppercase enums in regional_payment_profiles.json)
RAIL_CARD = "CARD"
RAIL_BANK = "BANK"
RAIL_MTN_MOMO = "MTN_MOMO"
RAIL_ORANGE_MOMO = "ORANGE_MOMO"
RAIL_MPESA = "MPESA"
RAIL_CASH = "CASH"
RAIL_WALLET = "WALLET"
RAIL_PIX = "PIX"
RAIL_UPI = "UPI"
RAIL_INSTANT_BANK = "INSTANT_BANK"
RAIL_VOUCHER = "VOUCHER"
RAIL_MANUAL_PROOF = "MANUAL_PROOF"

CANONICAL_RAIL_CLASSES: frozenset[str] = frozenset(
    {
        "card",
        "bank",
        "mobile_money",
        "wallet",
        "instant_bank",
        "voucher",
        "cash",
        "manual_proof",
    }
)

PROFILE_RAIL_TO_CANONICAL: dict[str, str] = {
    RAIL_CARD: "card",
    RAIL_BANK: "bank",
    RAIL_MTN_MOMO: "mobile_money",
    RAIL_ORANGE_MOMO: "mobile_money",
    RAIL_MPESA: "mobile_money",
    RAIL_CASH: "cash",
    RAIL_WALLET: "wallet",
    RAIL_PIX: "instant_bank",
    RAIL_UPI: "wallet",
    RAIL_INSTANT_BANK: "instant_bank",
    RAIL_VOUCHER: "voucher",
    RAIL_MANUAL_PROOF: "manual_proof",
}

MODEL_RAIL_KIND_TO_CANONICAL: dict[str, str] = {
    "CARD": "card",
    "BANK_TRANSFER": "bank",
    "MOBILE_MONEY": "mobile_money",
    "CASH": "cash",
    "WALLET": "wallet",
    "MANUAL": "manual_proof",
}

PSP_SLUG_PRIMARY_CANONICAL: dict[str, str] = {
    "stripe": "card",
    "paystack": "bank",
    "flutterwave": "bank",
    "mtn_momo": "mobile_money",
    "orange_money": "mobile_money",
    "mpesa-daraja": "mobile_money",
    "razorpay": "wallet",
    "pesapal": "mobile_money",
    "mercado_pago": "wallet",
    "dlocal": "card",
    "adyen": "card",
    "paypal": "wallet",
}


def canonical_class_for_profile_rail(rail_code: str | None) -> str:
    key = str(rail_code or "").strip().upper()
    return PROFILE_RAIL_TO_CANONICAL.get(key, "bank")


def canonical_classes_for_profile(row: dict[str, Any] | None) -> list[str]:
    if not row:
        return ["bank", "cash", "manual_proof"]
    seen: list[str] = []
    for bucket in ("primary_rails", "backup_rails"):
        for rail in row.get(bucket) or []:
            cc = canonical_class_for_profile_rail(str(rail))
            if cc not in seen:
                seen.append(cc)
    if not seen:
        seen = ["bank", "cash"]
    if row.get("manual_fallback") and "manual_proof" not in seen:
        seen.append("manual_proof")
    return seen


def adapter_registry_parity_findings() -> list[str]:
    """Return gaps between PSP registry and taxonomy (for tests)."""
    from apps.billing.psp_adapter_registry import iter_psps

    findings: list[str] = []
    for psp in iter_psps():
        slug = psp.psp_slug
        if slug not in PSP_SLUG_PRIMARY_CANONICAL:
            findings.append(f"psp {slug} missing PSP_SLUG_PRIMARY_CANONICAL mapping")
        else:
            canonical = PSP_SLUG_PRIMARY_CANONICAL[slug]
            if canonical not in CANONICAL_RAIL_CLASSES:
                findings.append(f"psp {psp.slug} maps to invalid canonical {canonical}")
    return findings
