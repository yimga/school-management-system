"""
Profile-driven PSP evidence paths (SFDP Phase 3 — batch 1457).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.finance.payment_local_global_contract import apply_phase3_enrichment
from apps.finance.regional_payment_profiles import get_regional_profile

ROOT = Path(__file__).resolve().parent.parent.parent


def evidence_paths_for_country(country_code: str | None) -> list[dict[str, Any]]:
    raw = get_regional_profile(country_code) or {}
    profile = apply_phase3_enrichment(str(country_code or ""), raw)
    cc = str(profile.get("country_code") or country_code or "XX").lower()
    currency = str(profile.get("currency") or "USD").lower()
    rows: list[dict[str, Any]] = []
    for psp in _psps_for_profile(profile):
        rel = f"var/evidence/geos-99/psp/{psp}/phase1_{psp}_charge_{cc}.json"
        rows.append(
            {
                "psp_slug": psp,
                "country_code": profile.get("country_code"),
                "evidence_path": rel,
                "template_path": f"var/evidence/geos-99/psp/{psp}/phase1_{psp}_charge_evidence.template.json",
                "currency": currency,
            }
        )
    rows.append(
        {
            "kind": "live_reconciliation",
            "country_code": profile.get("country_code"),
            "evidence_path": "var/evidence/geos-99/psp/live_reconciliation_evidence.json",
            "template_path": "var/evidence/geos-99/psp/live_reconciliation_evidence.template.json",
        }
    )
    return rows


def _psps_for_profile(profile: dict[str, Any]) -> list[str]:
    cc = str(profile.get("country_code") or "").upper()
    rails = [str(r).upper() for r in (profile.get("primary_rails") or [])]
    psps: list[str] = []
    if cc in {"NG", "GH"} or "PAYSTACK" in " ".join(rails):
        psps.append("paystack")
    if cc in {"CM", "NG", "GH", "KE"} or "FLUTTERWAVE" in " ".join(rails):
        if "flutterwave" not in psps:
            psps.append("flutterwave")
    if "CARD" in rails or cc in {"US", "CA", "GB", "FR", "AE", "BR"}:
        psps.append("stripe")
    if "MTN_MOMO" in rails:
        psps.append("mtn_momo")
    if "ORANGE_MOMO" in rails:
        psps.append("orange_money")
    return psps or ["stripe"]


def ensure_evidence_template_refs() -> list[str]:
    """Return missing template paths (for tests)."""
    missing: list[str] = []
    for psp in ("stripe", "paystack", "flutterwave", "mtn_momo", "orange_money"):
        tpl = ROOT / f"var/evidence/geos-99/psp/{psp}/README.md"
        if not tpl.is_file():
            missing.append(str(tpl.relative_to(ROOT)))
    return missing
