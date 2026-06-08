"""
Country Readiness Register — the world-wide launch-readiness truth table.

This module does NOT declare new country data. It JOINS three existing
source-of-truth registers and computes, per ISO-3166 country, exactly what a
tenant must do (just add an API key in their config) versus what the platform
must build first (finish/certify a payment adapter, ship a locale, map a board).

Joined SOTs (read-only):
  * apps/finance/data/regional_payment_profiles.json  — 250 countries: currency,
    primary/backup payment rails, manual-fallback + reconciliation flags.
  * apps/billing/psp_adapter_registry.py              — every PSP adapter the
    platform can hand a tenant, its capabilities, settlement currencies, and
    `adapter_status` (live | in_progress | planned).
  * apps/siteconfig/local_experience_profiles.py      — per-country language /
    academic-system / grading bundle (curated subset).

The headline this surfaces honestly: a payment rail is only "config-only" for a
tenant once its adapter is `live`. Today every PSP row is `in_progress`/`planned`,
so the whole world is `adapter_in_progress` or `manual_only` — NOT "solved." The
moment one adapter flips to `live`, every country whose dominant rail + currency
it covers recomputes to GREEN automatically. That is the point of the register:
it turns "build 250 integrations" into "finish ~8 rails, then it is pure config."

Pure-Python (no Django import) so it is unit-testable and importable from the
operator view, the docs generator, and a CI coverage scanner alike.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Readiness tiers (the four answers a country row can resolve to)
# ---------------------------------------------------------------------------
TIER_CONFIG_ONLY = "config_only"          # GREEN  — tenant just adds an API key
TIER_ADAPTER_IN_PROGRESS = "adapter_in_progress"  # AMBER — platform must finish/certify a scaffolded rail
TIER_MANUAL_ONLY = "manual_only"          # BLUE   — works today via manual receipts; live rail is a build
TIER_PLATFORM_BUILD = "platform_build"    # RED    — no adapter maps to the country's rails at all
TIER_CORRIDOR_UNDEFINED = "corridor_undefined"  # GREY — payment corridor is still a placeholder stub;
#                                                  readiness is UNKNOWN until the corridor is researched.
#   This is the honesty tier. 235/250 rows in regional_payment_profiles.json are "SFDP Phase 2 stub"
#   placeholders carrying a fake USD/EUR currency + generic CARD/BANK rails. Crediting them as
#   adapter_in_progress (because a scaffolded global card PSP happens to settle their fake USD) inflates
#   the readiness picture. We surface them as their own tier so the headline counts only the corridors
#   we have actually defined — and so "define corridor X" is visible as DATA work, distinct from the
#   ADAPTER work of promoting a PSP to live.

TIER_LABELS = {
    TIER_CONFIG_ONLY: "Config-only (tenant self-serve)",
    TIER_ADAPTER_IN_PROGRESS: "Config-blocked (platform must finish the rail)",
    TIER_MANUAL_ONLY: "Manual-only today (live rail is a platform build)",
    TIER_PLATFORM_BUILD: "Platform build required (no adapter)",
    TIER_CORRIDOR_UNDEFINED: "Corridor undefined (placeholder data — research first)",
}
TIER_TONE = {
    TIER_CONFIG_ONLY: "success",
    TIER_ADAPTER_IN_PROGRESS: "warning",
    TIER_MANUAL_ONLY: "info",
    TIER_PLATFORM_BUILD: "danger",
    TIER_CORRIDOR_UNDEFINED: "secondary",
}
TIER_ORDER = (
    TIER_CONFIG_ONLY,
    TIER_ADAPTER_IN_PROGRESS,
    TIER_MANUAL_ONLY,
    TIER_PLATFORM_BUILD,
    TIER_CORRIDOR_UNDEFINED,
)

# ---------------------------------------------------------------------------
# Rail vocabulary (from regional_payment_profiles.json) → PSP capability/slug.
# A rail is "electronically collectable" only if a PSP adapter speaks it.
# CASH / MANUAL_PROOF / VOUCHER are operator-reconciled and never need a PSP.
# WALLET is the platform-native internal wallet (always available).
# ---------------------------------------------------------------------------
RAIL_CAPABILITY: dict[str, str] = {
    "CARD": "cards",
    "BANK": "bank_transfer",
    "INSTANT_BANK": "bank_transfer",
    "PIX": "bank_transfer",
    "UPI": "bank_transfer",
    "MTN_MOMO": "mobile_money",
    "ORANGE_MOMO": "mobile_money",
    "MPESA": "mobile_money",
    "WALLET": "_platform_native",
}
# Rails the operator settles by hand — always available, never a PSP gap.
MANUAL_RAILS = frozenset({"CASH", "MANUAL_PROOF", "VOUCHER"})
# Currency-/country-bound rails: a PSP only counts if it settles the local
# currency (mobile money + the national instant rails PIX/UPI are not portable).
# Card / bank / generic instant rails accept most currencies, so a scaffolded
# global PSP counts regardless of its (narrow, illustrative) settlement list.
CURRENCY_BOUND_RAILS = frozenset({"MTN_MOMO", "ORANGE_MOMO", "MPESA", "PIX", "UPI"})
# Rail slug hints — the canonical adapter a country leading with this rail needs
# promoted to live. Drives the "platform_action" + the by-blocking-PSP scoreboard.
RAIL_PREFERRED_PSP: dict[str, tuple[str, ...]] = {
    "MTN_MOMO": ("mtn_momo",),
    "ORANGE_MOMO": ("orange_money",),
    "MPESA": ("mpesa-daraja", "pesapal"),
    "UPI": ("razorpay",),
    "PIX": ("mercado_pago", "dlocal"),
    "CARD": ("stripe", "adyen", "paypal"),
    "BANK": ("stripe", "adyen", "dlocal"),
    "INSTANT_BANK": ("adyen", "dlocal", "stripe"),
}

_DATA_PATH = Path(__file__).resolve().parent / "data" / "regional_payment_profiles.json"


@lru_cache(maxsize=1)
def _payment_profiles() -> dict[str, dict[str, Any]]:
    with _DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _psp_rows() -> tuple[Any, ...]:
    from apps.billing.psp_adapter_registry import iter_psps

    return tuple(iter_psps())


@lru_cache(maxsize=1)
def _supported_locales() -> frozenset[str]:
    """Language codes the platform declares (Django LANGUAGES). Declared ≠ fully
    translated — completeness is reported separately by scan_locale_coverage."""
    try:
        from django.conf import settings

        return frozenset(code for code, _ in getattr(settings, "LANGUAGES", []))
    except Exception:  # noqa: BLE001 - settings may be unconfigured in a bare unit test
        return frozenset({"en"})


def _experience_profile(country_code: str) -> dict[str, Any] | None:
    try:
        from apps.siteconfig.local_experience_profiles import list_profiles

        rows = list_profiles(country=country_code)
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001 - profiles registry is optional context
        return None


def _languages_for_country(country_code: str) -> list[str]:
    """UNION of declared languages across EVERY experience profile for this country.

    A country can carry more than one profile (e.g. CM has anglophone-GCE + francophone-BAC,
    IN has CBSE-Hindi + Karnataka-state). The old `rows[0]` pick silently dropped the second
    profile's languages, so a bilingual market looked half-localized. Union, dedupe, preserve order.
    """
    try:
        from apps.siteconfig.local_experience_profiles import list_profiles

        rows = list_profiles(country=country_code)
    except Exception:  # noqa: BLE001 - profiles registry is optional context
        return []
    seen: dict[str, None] = {}
    for r in rows:
        for lang in r.get("languages") or []:
            seen.setdefault(lang, None)
    return list(seen.keys())


# A payment corridor is a PLACEHOLDER (stub) when its profile notes flag it as one. 235/250 rows are
# `"SFDP Phase 2 stub — replace with corridor-specific rails before verified_live."` carrying a fake
# USD/EUR currency. The 15 DEFINED corridors are the markets whose rails/currency we have researched.
_PLACEHOLDER_NOTE_MARKERS = ("stub", "placeholder")


def _is_placeholder(profile: dict[str, Any]) -> bool:
    """A corridor is a placeholder when its corridor-definition `notes` flag it as a stub.

    Read `notes` ONLY, not `provider_notes`: those are two different axes. `notes` describes the
    CORRIDOR (currency + dominant rails); `provider_notes` describes PSP WIRING STATUS and carries a
    generic "Registry stub only" on many fully-defined corridors (e.g. Brazil: real BRL/PIX corridor,
    PSP not yet wired). Conflating them wrongly demotes researched markets to undefined."""
    return any(m in profile.get("notes", "").lower() for m in _PLACEHOLDER_NOTE_MARKERS)


def unclassified_rails() -> dict[str, list[str]]:
    """Coverage guard: every primary/backup rail in the payment SOT must be classified as
    electronic (RAIL_CAPABILITY), manual (MANUAL_RAILS), or platform-native. Returns
    {rail: [country_codes]} for any rail that falls through — empty dict = full coverage.

    Without this, a future data edit that introduces a new rail token (e.g. `"QRIS"`) would
    silently route every country using it to TIER_PLATFORM_BUILD with no warning. A test asserts
    this stays empty so the register can never quietly under-report a whole rail family."""
    classified = set(RAIL_CAPABILITY) | set(MANUAL_RAILS)
    out: dict[str, list[str]] = {}
    for cc, profile in _payment_profiles().items():
        rails = list(profile.get("primary_rails") or []) + list(profile.get("backup_rails") or [])
        for rail in rails:
            if rail not in classified:
                out.setdefault(rail, []).append(cc)
    return out


def _candidate_psps_for_rail(rail: str, currency: str) -> list[Any]:
    """PSP rows that can electronically collect this rail. Currency-settlement is
    honored when the adapter declares a whitelist; an empty whitelist = no limit."""
    capability = RAIL_CAPABILITY.get(rail)
    if not capability or capability == "_platform_native":
        return []
    preferred = RAIL_PREFERRED_PSP.get(rail, ())
    currency_bound = rail in CURRENCY_BOUND_RAILS
    out: list[Any] = []
    for psp in _psp_rows():
        if capability not in psp.capabilities:
            continue
        # Mobile-money / PIX / UPI only count if the adapter settles the local
        # currency. Card / bank rails accept most currencies, so a scaffolded
        # global PSP counts regardless of its narrow declared settlement list.
        if currency_bound:
            settles = (not psp.settlement_currencies) or (currency in psp.settlement_currencies)
            if not settles:
                continue
        out.append(psp)
    # Order: strongest status first (live must win), then the canonical preferred
    # adapter within that status tier, then slug for determinism.
    rank = {"live": 0, "in_progress": 1, "planned": 2}

    def _pref_idx(slug: str) -> int:
        return preferred.index(slug) if slug in preferred else len(preferred)

    out.sort(key=lambda p: (rank.get(p.adapter_status, 9), _pref_idx(p.psp_slug), p.psp_slug))
    return out


def _best_status(psps: list[Any], currency: str) -> tuple[str, Any | None]:
    """Return (status, psp) for the strongest adapter that settles `currency`.
    'live' requires a currency match; 'scaffolded' (in_progress/planned) does
    not — the adapter existing at all is the platform-work signal."""
    live = [p for p in psps if p.adapter_status == "live" and ((not p.settlement_currencies) or currency in p.settlement_currencies)]
    if live:
        return "live", live[0]
    scaffolded = [p for p in psps if p.adapter_status in ("in_progress", "planned")]
    if scaffolded:
        return scaffolded[0].adapter_status, scaffolded[0]
    return "none", None


def assess_country(country_code: str) -> dict[str, Any] | None:
    """Compute the readiness row for one ISO-2 country. Returns None if unknown."""
    cc = (country_code or "").strip().upper()
    profile = _payment_profiles().get(cc)
    if not profile:
        return None

    currency = str(profile.get("currency") or "")
    primary_rails = list(profile.get("primary_rails") or ([profile["primary_rail"]] if profile.get("primary_rail") else []))
    manual_ok = bool(profile.get("manual_fallback"))
    wallet_native = "WALLET" in primary_rails or "WALLET" in (profile.get("backup_rails") or [])

    # --- Payment assessment: walk each electronic rail this country uses. ---
    rail_findings: list[dict[str, Any]] = []
    best_overall = "none"
    blocking_psp: dict[str, str] | None = None
    for rail in primary_rails:
        if rail in MANUAL_RAILS:
            rail_findings.append({"rail": rail, "kind": "manual", "status": "manual", "psp": None})
            continue
        if RAIL_CAPABILITY.get(rail) == "_platform_native":
            rail_findings.append({"rail": rail, "kind": "platform_native", "status": "native", "psp": None})
            continue
        candidates = _candidate_psps_for_rail(rail, currency)
        status, psp = _best_status(candidates, currency)
        rail_findings.append({
            "rail": rail,
            "kind": "electronic",
            "status": status,
            "psp": psp.psp_slug if psp else None,
            "psp_label": psp.label if psp else None,
        })
        order = {"live": 3, "in_progress": 2, "planned": 1, "none": 0}
        if order[status] > order[best_overall]:
            best_overall = status
            if psp and status != "live":
                blocking_psp = {"slug": psp.psp_slug, "label": psp.label, "status": status}

    has_electronic_rail = any(f["kind"] == "electronic" for f in rail_findings)

    # --- Payment tier ---
    if best_overall == "live":
        payment_tier = TIER_CONFIG_ONLY
    elif best_overall in ("in_progress", "planned"):
        payment_tier = TIER_ADAPTER_IN_PROGRESS
    elif manual_ok or wallet_native:
        payment_tier = TIER_MANUAL_ONLY if has_electronic_rail or not wallet_native else TIER_CONFIG_ONLY
    else:
        payment_tier = TIER_PLATFORM_BUILD

    # --- Localization assessment (languages unioned across ALL profiles for the country) ---
    exp = _experience_profile(cc)
    languages = _languages_for_country(cc)
    supported = _supported_locales()
    if languages:
        covered = [lang for lang in languages if lang.split("-")[0] in supported]
        locale_state = "localized" if len(covered) == len(languages) else ("partial" if covered else "english_fallback")
    else:
        locale_state = "english_fallback"  # no profile → UI serves English (functional, not localized)
    academic_system = (exp.get("academic_system") if exp else None) or "generic"

    # --- Integration footguns the tenant must get right when wiring a PSP ---
    minor_units = profile.get("minor_units")
    zero_decimal = minor_units == 0  # XAF/XOF/JPY/KRW etc. — charging in "cents" overcharges 100×
    risk_tier = str(profile.get("risk_tier") or "")
    data_state = "placeholder" if _is_placeholder(profile) else "defined"

    # --- Overall tier: payments dominate launch-readiness; locale/board refine. ---
    overall = payment_tier
    # A live-payment country still flagged AMBER if its language is wholly unsupported.
    if overall == TIER_CONFIG_ONLY and locale_state == "english_fallback" and languages:
        overall = TIER_ADAPTER_IN_PROGRESS
    # Honesty override: a placeholder corridor's readiness is UNKNOWN — the accidental CARD/BANK rail
    # match on its fake USD currency is not a real signal. Report it as corridor_undefined, not AMBER.
    if data_state == "placeholder":
        overall = TIER_CORRIDOR_UNDEFINED

    # --- Human action strings ---
    if data_state == "placeholder":
        tenant_action = "Manual / offline receipts work today; live rail awaits a defined corridor."
        platform_action = f"Research the {cc} corridor (real currency, dominant rails, PSP) — this is data work, not an adapter build."
    elif payment_tier == TIER_CONFIG_ONLY:
        tenant_action = f"Add your {_rail_label(primary_rails)} merchant API credentials in Integrations → Payments."
        platform_action = "None — adapter is live."
    elif payment_tier == TIER_ADAPTER_IN_PROGRESS and blocking_psp:
        tenant_action = "Use manual / offline receipts until the live rail ships." if manual_ok else "Waiting on the platform rail."
        platform_action = f"Promote the {blocking_psp['label']} adapter ({blocking_psp['status']}) to live (request-to-pay → webhook → reconcile → split)."
    elif payment_tier == TIER_MANUAL_ONLY:
        tenant_action = "Configure manual payment instructions (bank / MoMo number); reconcile receipts."
        platform_action = f"Build a {_rail_label(primary_rails)} adapter to enable live collection."
    else:
        tenant_action = "Cash / manual receipts only."
        platform_action = f"No adapter maps to {currency} rails — scope a PSP."

    return {
        "country_code": cc,
        "label": profile.get("label") or cc,
        "currency": currency,
        "primary_rails": primary_rails,
        "manual_fallback": manual_ok,
        "offline_receipt_allowed": bool(profile.get("offline_receipt_allowed")),
        "reconciliation_required": bool(profile.get("reconciliation_required")),
        "rail_findings": rail_findings,
        "blocking_psp": blocking_psp,
        "payment_tier": payment_tier,
        "data_state": data_state,
        "minor_units": minor_units,
        "zero_decimal": zero_decimal,
        "risk_tier": risk_tier,
        "languages": languages,
        "locale_state": locale_state,
        "academic_system": academic_system,
        "has_experience_profile": exp is not None,
        "overall_tier": overall,
        "overall_label": TIER_LABELS[overall],
        "overall_tone": TIER_TONE[overall],
        "tenant_action": tenant_action,
        "platform_action": platform_action,
    }


def _rail_label(rails: list[str]) -> str:
    pretty = {
        "MTN_MOMO": "MTN MoMo", "ORANGE_MOMO": "Orange Money", "MPESA": "M-Pesa",
        "CARD": "card", "BANK": "bank transfer", "INSTANT_BANK": "instant bank",
        "PIX": "PIX", "UPI": "UPI", "WALLET": "wallet",
    }
    electronic = [pretty.get(r, r.title()) for r in rails if r not in MANUAL_RAILS]
    return " / ".join(electronic[:3]) if electronic else "manual"


@lru_cache(maxsize=1)
def all_assessments() -> dict[str, dict[str, Any]]:
    """Every country, keyed by ISO-2, sorted by country code."""
    out: dict[str, dict[str, Any]] = {}
    for cc in sorted(_payment_profiles().keys()):
        row = assess_country(cc)
        if row:
            out[cc] = row
    return out


def summary() -> dict[str, Any]:
    """Aggregate readiness across the whole world for the operator scoreboard.

    Leverage / locale / risk rollups are computed over the DEFINED corridors only — counting
    placeholder stubs (235/250) would inflate every number (the classic "Stripe covers 240" artifact
    that was really just 200 stubs sharing a fake USD currency). `by_tier` and `by_data_state` still
    span all 250 so the placeholder backlog stays visible."""
    rows = list(all_assessments().values())
    defined = [r for r in rows if r["data_state"] == "defined"]

    by_tier = {t: 0 for t in TIER_ORDER}
    by_data_state = {"defined": 0, "placeholder": 0}
    by_blocking_psp: dict[str, int] = {}
    by_locale: dict[str, int] = {}
    by_risk_tier: dict[str, int] = {}
    for r in rows:
        by_tier[r["overall_tier"]] = by_tier.get(r["overall_tier"], 0) + 1
        by_data_state[r["data_state"]] = by_data_state.get(r["data_state"], 0) + 1
    for r in defined:  # honest rollups — defined corridors only
        bp = r.get("blocking_psp")
        if bp:
            by_blocking_psp[bp["label"]] = by_blocking_psp.get(bp["label"], 0) + 1
        by_locale[r["locale_state"]] = by_locale.get(r["locale_state"], 0) + 1
        if r["risk_tier"]:
            by_risk_tier[r["risk_tier"]] = by_risk_tier.get(r["risk_tier"], 0) + 1

    from apps.billing.psp_adapter_registry import status_counts as psp_status_counts

    return {
        "total_countries": len(rows),
        "defined_corridors": len(defined),
        "placeholder_corridors": len(rows) - len(defined),
        "by_tier": by_tier,
        "by_data_state": by_data_state,
        "by_blocking_psp": dict(sorted(by_blocking_psp.items(), key=lambda kv: -kv[1])),
        "by_locale": by_locale,
        "by_risk_tier": dict(sorted(by_risk_tier.items(), key=lambda kv: -kv[1])),
        "psp_status_counts": psp_status_counts(),
        "live_rail_count": psp_status_counts().get("live", 0),
        "tier_labels": TIER_LABELS,
        "tier_tone": TIER_TONE,
        "tier_order": list(TIER_ORDER),
    }
