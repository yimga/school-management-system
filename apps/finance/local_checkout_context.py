"""Checkout rail card context for parent invoice pay surface (SFDP 1454)."""

from __future__ import annotations

from typing import Any

from apps.finance.payment_local_global_contract import apply_phase3_enrichment
from apps.finance.payment_risk_tier import evaluate_risk
from apps.finance.regional_payment_profiles import get_regional_profile


def build_checkout_rail_cards(country_code: str | None) -> dict[str, Any]:
    raw = get_regional_profile(country_code) or {}
    profile = apply_phase3_enrichment(str(country_code or ""), raw)
    vocab = profile.get("local_rail_vocabulary") or {}
    order = profile.get("checkout_rail_order") or profile.get("primary_rails") or []
    risk = evaluate_risk(profile)
    cards: list[dict[str, Any]] = []
    for idx, rail in enumerate(order):
        code = str(rail).upper()
        cards.append(
            {
                "rail_code": code,
                "label": vocab.get(code) or vocab.get(rail) or code.replace("_", " ").title(),
                "tier": "primary" if idx < len(profile.get("primary_rails") or []) else "backup",
                "canonical_class": profile.get("canonical_rail_classes", ["bank"])[0]
                if profile.get("canonical_rail_classes")
                else "bank",
            }
        )
    if profile.get("manual_fallback"):
        cards.append(
            {
                "rail_code": "MANUAL_PROOF",
                "label": vocab.get("MANUAL_PROOF", "Upload proof / cash desk"),
                "tier": "fallback",
                "canonical_class": "manual_proof",
            }
        )
    return {
        "cards": cards,
        "profile": profile,
        "risk": risk,
        "currency_display": profile.get("currency_display"),
        "fx_disclaimer": "",
    }


def payment_method_choices(country_code: str | None) -> list[tuple[str, str]]:
    bundle = build_checkout_rail_cards(country_code)
    out: list[tuple[str, str]] = []
    for card in bundle["cards"]:
        out.append((card["rail_code"], card["label"]))
    return out
