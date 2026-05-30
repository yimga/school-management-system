#!/usr/bin/env python3
"""Extend every country shard + the master matrix with Phase 0X regulatory and provenance blocks.

Adds:
  - regulatory_matrix (privacy / age_of_digital_consent / biometric / AI / SMS / tax / sanctions /
    records retention / content safety / accessibility)
  - provenance (source / effective_from / effective_to / verified_at / verified_by)
  - edge_jurisdiction_flags (sovereign / disputed / virtual / refugee_nomadic)
  - exam_boards (list — empty by default, T1 anchors get seeded)
  - legacy_mis_incumbents (list — empty by default, T1 anchors get seeded)
  - national_identity_brokers (list — empty by default, T1 anchors get seeded)
  - calendar_sources (list — public-holiday source registry)
  - labor_law (employer_of_record / payroll_authority / cross_school_employment_allowed)
  - regional_languages (list — beyond constitutional official)
  - dr_rto_rpo (rto_minutes / rpo_minutes / cross_region_failover_allowed)
  - pricing_band (PPP-adjusted band + FX hedge band)
  - risk_signals (top_risks list with probability / impact / detectability)

Idempotent: skips fields that already exist. Run after the skeleton bootstrap.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger("extend_regulatory_block")

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
MASTER_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"

EU_EEA_ISO = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
    "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK", "IS", "LI", "NO",
})
GDPR_LIKE_NON_EEA = frozenset({"GB", "CH"})

PRIVACY_REGIMES_BY_ISO: dict[str, list[str]] = {
    "US": ["FERPA", "COPPA", "PPRA", "state_dpa_eg_sopipa_eg_uciipa"],
    "CA": ["PIPEDA", "provincial_eg_FIPPA_PIPA_la25"],
    "BR": ["LGPD"],
    "IN": ["DPDP_Act_2023"],
    "SG": ["PDPA"],
    "MY": ["PDPA_2010"],
    "PH": ["DPA_2012"],
    "TH": ["PDPA_2019"],
    "JP": ["APPI"],
    "KR": ["PIPA"],
    "AU": ["Privacy_Act_1988", "Australian_Privacy_Principles"],
    "NZ": ["Privacy_Act_2020"],
    "ZA": ["POPIA"],
    "NG": ["NDPA_2023"],
    "KE": ["DPA_2019"],
    "IL": ["Privacy_Protection_Law_5741_1981"],
    "CN": ["PIPL", "DSL", "CSL"],
    "RU": ["Federal_Law_152_FZ"],
    "TR": ["KVKK"],
    "EG": ["PDP_Law_151_2020"],
    "MX": ["LFPDPPP"],
    "AR": ["Law_25_326"],
    "CL": ["Law_19_628"],
}

AGE_OF_CONSENT_BY_ISO: dict[str, int] = {
    "US": 13, "GB": 13, "IE": 16, "DE": 16, "ES": 14, "FR": 15, "IT": 14,
    "NL": 16, "BE": 13, "AT": 14, "PT": 13, "PL": 16, "CZ": 15, "DK": 13,
    "SE": 13, "FI": 13, "GR": 15, "HU": 16, "RO": 16, "SK": 16, "BG": 14,
    "HR": 16, "EE": 13, "LT": 14, "LV": 13, "LU": 16, "MT": 13, "CY": 14,
    "SI": 15, "NO": 13, "IS": 13, "CH": 16, "JP": 13, "KR": 14, "AU": 15,
    "NZ": 13, "BR": 13, "CA": 13, "IN": 18, "ZA": 18, "MX": 18, "CL": 14,
}


def _privacy_regimes(iso: str, is_eu_eea: bool) -> list[str]:
    listed = list(PRIVACY_REGIMES_BY_ISO.get(iso, []))
    if is_eu_eea or iso in GDPR_LIKE_NON_EEA:
        if "GDPR" not in listed:
            listed.insert(0, "GDPR")
    if not listed:
        listed = ["generic_no_specific_statute_documented"]
    return listed


def _ai_regulation(iso: str, is_eu_eea: bool) -> dict[str, Any]:
    if is_eu_eea:
        return {
            "regime": "EU_AI_Act_2024",
            "ed_tech_risk_class": "varies_high_risk_when_admissions_or_assessment",
            "citation": "Regulation (EU) 2024/1689",
        }
    if iso == "CN":
        return {
            "regime": "Algorithmic_Recommendation_Registry_2022",
            "ed_tech_risk_class": "filing_required",
            "citation": "CAC + multi-ministry administrative measures",
        }
    if iso == "US":
        return {
            "regime": "state_by_state_plus_federal_EO",
            "ed_tech_risk_class": "varies_by_state",
            "citation": "EO 14110 + NIST AI RMF + state EOs",
        }
    if iso == "GB":
        return {
            "regime": "AI_Regulatory_Principles_pro_innovation_white_paper",
            "ed_tech_risk_class": "regulator_specific_eg_ICO_Ofqual_DfE",
            "citation": "AI Regulation White Paper 2023 + ICO guidance",
        }
    return {
        "regime": "no_dedicated_statute_documented",
        "ed_tech_risk_class": "unspecified",
        "citation": None,
    }


def _sms_telecom_rule(iso: str, is_eu_eea: bool) -> dict[str, Any]:
    if iso == "US":
        return {"regime": "TCPA", "opt_in": "implied_with_clear_disclosure", "citation": "47 USC 227"}
    if iso == "CA":
        return {"regime": "CASL", "opt_in": "express", "citation": "S.C. 2010 c. 23"}
    if is_eu_eea or iso in GDPR_LIKE_NON_EEA:
        return {"regime": "ePrivacy_Directive_2002_58_EC", "opt_in": "express", "citation": "Directive 2002/58/EC"}
    if iso == "IN":
        return {"regime": "TRAI_TCCCPR_DLT_Headers_Required", "opt_in": "implied_with_DLT_registration", "citation": "TRAI TCCCPR 2018"}
    if iso == "AU":
        return {"regime": "Spam_Act_2003", "opt_in": "express", "citation": "Spam Act 2003 (Cth)"}
    return {"regime": "no_dedicated_statute_documented", "opt_in": "unspecified", "citation": None}


def _accessibility_statute(iso: str, is_eu_eea: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "platform_baseline": "WCAG_2_2_AA",
        "local_statutes": [],
        "sign_languages": [],
    }
    statutes_by_iso: dict[str, list[str]] = {
        "US": ["Section_508", "ADA_Title_III"],
        "GB": ["Equality_Act_2010", "PSBAR_2018"],
        "FR": ["RGAA_4_1", "Loi_handicap_2005"],
        "JP": ["JIS_X_8341_3"],
        "CA": ["AODA_Ontario_Information_and_Communications_Standard", "ACA_Federal"],
        "AU": ["DDA_1992"],
        "IL": ["IS_5568"],
    }
    if iso in statutes_by_iso:
        out["local_statutes"] = statutes_by_iso[iso]
    if is_eu_eea:
        out["local_statutes"] = out["local_statutes"] + ["EAA_2025"]

    sign_lang_by_iso: dict[str, list[str]] = {
        "US": ["ASL"], "GB": ["BSL"], "AU": ["Auslan"], "NZ": ["NZSL"],
        "FR": ["LSF"], "DE": ["DGS"], "JP": ["JSL"], "ES": ["LSE", "LSC"],
        "BR": ["Libras"], "IL": ["ISL"], "PT": ["LGP"], "IT": ["LIS"],
    }
    if iso in sign_lang_by_iso:
        out["sign_languages"] = sign_lang_by_iso[iso]
    return out


def _records_retention_years(iso: str) -> dict[str, int]:
    base = {"transcript_years": 0, "attendance_years": 5, "financial_years": 7, "safeguarding_years": 25}
    if iso in {"US", "GB", "CA", "AU", "NZ"}:
        base["transcript_years"] = 999
    elif iso in {"BR", "MX", "AR", "CL", "ZA", "IN", "JP", "KR"}:
        base["transcript_years"] = 60
    else:
        base["transcript_years"] = 30
    return base


def _sanctions_status(iso: str) -> dict[str, Any]:
    high_risk = {"KP", "IR", "SY", "CU", "RU", "BY", "VE", "MM"}
    partial = {"AF", "SD", "ZW", "IQ", "LY"}
    if iso in high_risk:
        return {"status": "comprehensive_or_targeted_regime", "regimes": ["OFAC", "EU", "UN", "UK_OFSI"], "onboarding_block": True}
    if iso in partial:
        return {"status": "targeted_regime", "regimes": ["OFAC", "EU", "UN"], "onboarding_block": False}
    return {"status": "no_restriction_documented", "regimes": [], "onboarding_block": False}


def _content_safety_regime(iso: str, is_eu_eea: bool) -> dict[str, Any]:
    if is_eu_eea:
        return {"regime": "DSA", "citation": "Regulation (EU) 2022/2065"}
    if iso == "GB":
        return {"regime": "Online_Safety_Act_2023", "citation": "OSA 2023"}
    if iso == "IN":
        return {"regime": "IT_Rules_2021", "citation": "Information Technology Rules 2021"}
    if iso == "DE":
        return {"regime": "NetzDG", "citation": "Netzwerkdurchsetzungsgesetz"}
    if iso == "US":
        return {"regime": "Section_230_plus_state_minor_protection", "citation": "47 USC 230 + state acts"}
    return {"regime": "no_dedicated_statute_documented", "citation": None}


def _build_regulatory_matrix(row: dict[str, Any]) -> dict[str, Any]:
    iso = str(row.get("iso_alpha2") or "")
    is_eu_eea = iso in EU_EEA_ISO
    consent_age = AGE_OF_CONSENT_BY_ISO.get(iso, 13)
    return {
        "student_privacy_regimes": _privacy_regimes(iso, is_eu_eea),
        "age_of_digital_consent": consent_age,
        "biometric_data_rule": "parental_consent" if iso not in {"IL"} else "school_consent",
        "ai_regulation": _ai_regulation(iso, is_eu_eea),
        "sms_telecom_rule": _sms_telecom_rule(iso, is_eu_eea),
        "tax_reporting_obligations": [],
        "sanctions_status": _sanctions_status(iso),
        "records_retention_years": _records_retention_years(iso),
        "content_safety_regime": _content_safety_regime(iso, is_eu_eea),
        "accessibility_statute": _accessibility_statute(iso, is_eu_eea),
    }


def _build_provenance(row: dict[str, Any]) -> dict[str, Any]:
    iso = str(row.get("iso_alpha2") or "")
    is_sovereign = bool(row.get("sovereign_state"))
    return {
        "source": {
            "type": "matrix_skeleton_seed_v1",
            "citation_required_for_promotion": True,
            "notes": "Phase 0X requires every material claim to carry a primary-source citation before P0D close.",
        },
        "effective_from": None,
        "effective_to": None,
        "verified_at": None,
        "verified_by": "agent:bootstrap" if is_sovereign else "agent:bootstrap_territory",
        "iso_alpha2_ref": iso,
    }


def _build_edge_jurisdiction_flags(row: dict[str, Any]) -> dict[str, Any]:
    iso = str(row.get("iso_alpha2") or "")
    disputed = iso in {"EH", "PS", "XK", "TW"}
    return {
        "sovereign_state": bool(row.get("sovereign_state")),
        "territory": bool(row.get("territory")),
        "disputed_recognition": disputed,
        "online_only_virtual_school_supported": True,
        "refugee_nomadic_ed_supported": True,
        "antarctica_research_only": iso == "AQ",
        "disputed_regions": [],
    }


def _build_labor_law(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "employer_of_record_options": ["school", "district", "state", "org", "peo"],
        "payroll_authority": "school",
        "working_time_rule": "country_specific_citation_required",
        "severance_formula": "country_specific_citation_required",
        "collective_bargaining_presence": "unspecified",
        "cross_school_employment_allowed": True,
        "non_compete_enforceable": None,
    }


def _build_dr_rto_rpo(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rto_minutes": 240,
        "rpo_minutes": 60,
        "cross_region_failover_allowed": True,
        "counsel_signed_continuity_table": "external_required",
        "residency_label": "metadata_only_until_physical_pinning_lands",
    }


def _build_pricing_band(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ppp_band": "default_universal_band_until_research_complete",
        "fx_hedge_band_pct": 5,
        "local_currency_required": False,
    }


def _build_risk_signals(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "top_risks": [],
        "next_review_due": None,
    }


def _ensure_block(row: dict[str, Any], key: str, builder) -> bool:
    if key in row and isinstance(row[key], (dict, list)) and row[key]:
        return False
    row[key] = builder(row)
    return True


def _ensure_list(row: dict[str, Any], key: str) -> bool:
    if key in row and isinstance(row[key], list):
        return False
    row[key] = []
    return True


def _process_row(row: dict[str, Any]) -> dict[str, int]:
    added: dict[str, int] = {}
    blocks: list[tuple[str, Any]] = [
        ("regulatory_matrix", _build_regulatory_matrix),
        ("provenance", _build_provenance),
        ("edge_jurisdiction_flags", _build_edge_jurisdiction_flags),
        ("labor_law", _build_labor_law),
        ("dr_rto_rpo", _build_dr_rto_rpo),
        ("pricing_band", _build_pricing_band),
        ("risk_signals", _build_risk_signals),
    ]
    for key, builder in blocks:
        if _ensure_block(row, key, builder):
            added[key] = 1

    list_keys = (
        "exam_boards",
        "legacy_mis_incumbents",
        "national_identity_brokers",
        "calendar_sources",
        "regional_languages",
    )
    for key in list_keys:
        if _ensure_list(row, key):
            added[key] = 1
    return added


def _iter_shard_paths() -> Iterable[Path]:
    if not SHARD_DIR.is_dir():
        return []
    return sorted(SHARD_DIR.glob("*.json"))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    shard_paths = list(_iter_shard_paths())
    LOGGER.info("found %d shards", len(shard_paths))

    shard_changes = 0
    field_additions: dict[str, int] = {}
    for path in shard_paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        added = _process_row(row)
        if added:
            shard_changes += 1
            for key, count in added.items():
                field_additions[key] = field_additions.get(key, 0) + count
            path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")

    if MASTER_PATH.is_file():
        master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        rows = master.get("rows") or master.get("items") or master.get("countries") or []
        if isinstance(rows, list):
            master_changes = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                added = _process_row(row)
                if added:
                    master_changes += 1
            if master_changes:
                master["regenerated_at"] = datetime.now(timezone.utc).isoformat()
                MASTER_PATH.write_text(json.dumps(master, indent=2) + "\n", encoding="utf-8")
                LOGGER.info("master matrix updated rows=%d", master_changes)

    LOGGER.info("shards updated: %d / %d", shard_changes, len(shard_paths))
    for key, count in sorted(field_additions.items()):
        LOGGER.info("  + %s on %d shards", key, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
