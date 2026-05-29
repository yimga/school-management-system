#!/usr/bin/env python3
"""Phase 0C — enrich country governance matrix with languages, terminology, formats."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
LEDGER_PATH = REPO / "docs" / "generated" / "country_dissection_ledger.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from lib.global_governance_africa_overrides import AFRICA_GOVERNANCE_OVERRIDES  # noqa: E402
from lib.global_governance_continent_defaults import apply_continent_defaults  # noqa: E402
from lib.global_governance_geo import continent_and_wave_for_alpha2  # noqa: E402

_RTL_LANGS = frozenset({"ar", "he", "fa", "ur", "ps", "yi", "dv", "ku", "sd", "ug", "iw"})
_CORE_TERM_KEYS = (
    "teacher",
    "principal",
    "term",
    "report_card",
    "grade_level",
    "student",
    "classroom",
    "ministry_name",
)


def _bootstrap_django() -> None:
    import django

    django.setup()


def _lang_label_en(code: str) -> str:
    code = (code or "").strip().lower()
    if not code:
        return ""
    try:
        import pycountry

        lang = pycountry.languages.get(alpha_2=code)
        if lang:
            return str(lang.name)
        lang = pycountry.languages.get(alpha_3=code)
        if lang:
            return str(lang.name)
    except Exception:
        pass
    return code


def _iso639_from_geonames_token(token: str) -> str | None:
    token = (token or "").strip().lower()
    if not token:
        return None
    if len(token) == 2:
        return token
    try:
        import pycountry

        lang = pycountry.languages.get(alpha_3=token)
        if lang and getattr(lang, "alpha_2", None):
            return str(lang.alpha_2).lower()
    except Exception:
        pass
    return token[:2] if len(token) >= 2 else None


def _language_entry_from_seed(lang: dict[str, Any]) -> dict[str, Any]:
    code = str(lang.get("code") or "").lower()
    native = str(lang.get("native_name") or _lang_label_en(code))
    role = "official" if lang.get("is_official", True) else "national"
    if lang.get("education_system"):
        role = "education_medium"
    direction = "rtl" if code in _RTL_LANGS else "ltr"
    return {
        "iso639": code,
        "label_native": native,
        "label_en": _lang_label_en(code),
        "role": role,
        "script": "Arab" if direction == "rtl" and code == "ar" else "Latn",
        "direction": direction,
    }


def _fallback_languages(alpha2: str) -> list[dict[str, Any]]:
    """pycountry + geonamescache fallback when COUNTRY_LANGUAGES has no entry."""
    from lib.global_governance_geo import _geonames_by_iso2

    codes: list[str] = []
    geo = _geonames_by_iso2().get(alpha2.upper()) or {}
    raw_langs = str(geo.get("languages") or "")
    for token in raw_langs.split(","):
        iso = _iso639_from_geonames_token(token.strip())
        if iso and iso not in codes:
            codes.append(iso)

    if not codes:
        try:
            import pycountry

            country = pycountry.countries.get(alpha_2=alpha2.upper())
            if country:
                # pycountry has no official languages on country; use English as last resort.
                codes = ["en"]
        except Exception:
            codes = ["en"]

    if not codes:
        codes = ["en"]

    return [
        {
            "iso639": code,
            "label_native": _lang_label_en(code),
            "label_en": _lang_label_en(code),
            "role": "official" if idx == 0 else "co_official",
            "script": "Latn",
            "direction": "rtl" if code in _RTL_LANGS else "ltr",
        }
        for idx, code in enumerate(codes)
    ]


def sync_languages_for_row(alpha2: str, row: dict[str, Any]) -> None:
    """Populate official_languages, education_languages, languages_expected."""
    from apps.siteconfig._seed_country_languages import COUNTRY_LANGUAGES

    code = alpha2.upper()
    seed_langs = COUNTRY_LANGUAGES.get(code) or []

    if seed_langs:
        row["languages_expected"] = [str(l.get("code") or "").lower() for l in seed_langs if l.get("code")]
        row["official_languages"] = [_language_entry_from_seed(l) for l in seed_langs]
        edu_codes: list[str] = []
        for lang in seed_langs:
            lang_code = str(lang.get("code") or "").lower()
            if lang.get("education_system") or lang.get("is_official"):
                if lang_code and lang_code not in edu_codes:
                    edu_codes.append(lang_code)
        row["education_languages"] = edu_codes or list(row["languages_expected"])
    else:
        fallback = _fallback_languages(code)
        row["official_languages"] = fallback
        row["languages_expected"] = [str(e["iso639"]) for e in fallback]
        row["education_languages"] = list(row["languages_expected"])


def _term_to_multilang(value: Any, lang_code: str) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if v}
    if value:
        return {lang_code: str(value)}
    return {}


def sync_terminology_for_row(alpha2: str, row: dict[str, Any]) -> None:
    """Populate local_terminology from COUNTRY_LOCALIZATION + education system labels."""
    from apps.siteconfig import _seed_country_localization as seed
    from apps.siteconfig.country_localization_service import resolve_country_pack

    code = alpha2.upper()
    pack = seed.COUNTRY_LOCALIZATION.get(code) or resolve_country_pack(code)
    primary_lang = "en"
    if row.get("languages_expected"):
        primary_lang = str(row["languages_expected"][0])
    elif row.get("official_languages"):
        primary_lang = str(row["official_languages"][0].get("iso639") or "en")

    term: dict[str, Any] = {
        "teacher": {},
        "principal": {},
        "term": {},
        "report_card": {},
        "grade_level": {},
        "student": {},
        "classroom": {},
        "ministry_name": {},
        "admin_level_labels": [],
        "school_type_labels": [],
    }

    pack_term = dict(pack.get("terminology") or {})
    for key in ("teacher", "principal", "term", "report_card", "grade_level", "student", "classroom"):
        if key in pack_term:
            term[key] = _term_to_multilang(pack_term[key], primary_lang)

    # Per-language education_system terminology overlays
    for lang in pack.get("languages") or []:
        lang_code = str(lang.get("code") or primary_lang).lower()
        edu = lang.get("education_system") or {}
        edu_term = edu.get("terminology") or {}
        for key in ("teacher", "principal", "term", "report_card", "grade_level"):
            if key in edu_term:
                existing = term.get(key) or {}
                existing.update(_term_to_multilang(edu_term[key], lang_code))
                term[key] = existing

    # English fallbacks for any missing core keys
    english_defaults = {
        "teacher": "Teacher",
        "principal": "Principal",
        "term": "Term",
        "report_card": "Report card",
        "grade_level": "Grade level",
        "student": "Student",
        "classroom": "Classroom",
        "ministry_name": "Ministry of Education",
    }
    for key, default in english_defaults.items():
        if not term.get(key):
            term[key] = {"en": default}
        elif "en" not in term[key]:
            term[key]["en"] = default

    # School type labels from pack
    school_types = pack.get("school_types") or []
    term["school_type_labels"] = [
        {"code": st.get("code"), "label": st.get("label")}
        for st in school_types
        if st.get("label")
    ]

    # Admin level labels from row admin_levels if present
    admin_labels = []
    for level in row.get("admin_levels") or []:
        label_en = level.get("label_en") or ""
        label_local = level.get("label_local") or {}
        if label_en or label_local:
            admin_labels.append({"level": level.get("level"), "label_en": label_en, "label_local": label_local})
    term["admin_level_labels"] = admin_labels

    row["local_terminology"] = term
    if code in seed.COUNTRY_LOCALIZATION:
        row["terminology_source"] = "seed_pack"
    elif "regional" in str(pack.get("_pack_source") or pack.get("pack_source") or ""):
        row["terminology_source"] = "seed_pack"
    else:
        row["terminology_source"] = "matrix_research"

    # Calendar notes from pack
    cal = pack.get("calendar_system") or {}
    if cal:
        parts = [str(cal.get("label") or "")]
        if cal.get("term_names"):
            parts.append("Terms: " + ", ".join(str(t) for t in cal["term_names"]))
        if cal.get("academic_year_starts_month"):
            parts.append(f"Year starts month {cal['academic_year_starts_month']}")
        row["calendar_notes"] = "; ".join(p for p in parts if p)


def sync_formats_for_row(alpha2: str, row: dict[str, Any]) -> None:
    """Populate phone_country_code, name_order, address_format_key from country_formats_service."""
    from apps.siteconfig.country_formats_service import (
        ADDRESS_ORDER_BY_COUNTRY,
        dial_code_for,
        name_order_for,
        postal_code_label_for,
    )

    code = alpha2.upper()
    row["name_order"] = name_order_for(code)
    row["phone_country_code"] = dial_code_for(code)
    row["postal_label"] = postal_code_label_for(code)
    row["address_format_key"] = code if code in ADDRESS_ORDER_BY_COUNTRY else "generic"


def _resolve_pack_tier(alpha2: str) -> str:
    from apps.siteconfig import _seed_country_localization as seed
    from apps.siteconfig.country_localization_service import resolve_country_pack

    if alpha2 in seed.COUNTRY_LOCALIZATION:
        return "tier1_native"
    pack = resolve_country_pack(alpha2)
    source = str(pack.get("_pack_source") or pack.get("pack_source") or "")
    if "regional" in source:
        return "tier1_regional_clone"
    return "generic_fallback"


def apply_africa_governance_override(alpha2: str, row: dict[str, Any]) -> bool:
    """Merge W-Africa GEO overrides when present."""
    code = alpha2.upper()
    if str(row.get("continent") or "") != "Africa":
        return False
    override = AFRICA_GOVERNANCE_OVERRIDES.get(code)
    if not override:
        return False
    for key, value in override.items():
        row[key] = value
    row["dissection_wave"] = "W-Africa"
    risks = [r for r in (row.get("customer_risks") or []) if r != "skeleton_row_requires_dissection"]
    row["customer_risks"] = risks
    return True


def passes_governance_quality_gate(row: dict[str, Any]) -> bool:
    archetype = str(row.get("governance_archetype") or "")
    if archetype not in {
        "single_org_multi_site",
        "district_trust_overlay",
        "federation_equals",
        "state_emis_hub",
    }:
        return False
    if not row.get("employer_model"):
        return False
    if not row.get("reporting_chain"):
        return False
    if not row.get("recommended_operating_mode"):
        return False
    levels = row.get("admin_levels") or []
    if row.get("territory"):
        return bool(levels)
    if row.get("sovereign_state") and not levels:
        return False
    return True


def passes_locale_quality_gate(row: dict[str, Any]) -> bool:
    """True when Phase 0C language/locality fields meet minimum bar."""
    if not row.get("official_languages"):
        return False
    if not row.get("languages_expected"):
        return False
    if not row.get("education_languages"):
        return False
    term = row.get("local_terminology") or {}
    for key in _CORE_TERM_KEYS:
        if not term.get(key):
            return False
    if row.get("terminology_source") == "skeleton":
        return False
    if not row.get("name_order"):
        return False
    if not row.get("address_format_key"):
        return False
    return True


def enrich_row(alpha2: str, row: dict[str, Any], *, apply_governance_defaults: bool = True) -> bool:
    """Run all sync passes; return True if row passes locale + governance quality gates."""
    sync_languages_for_row(alpha2, row)
    if apply_governance_defaults:
        if not apply_africa_governance_override(alpha2, row):
            apply_continent_defaults(alpha2, row)
    sync_terminology_for_row(alpha2, row)
    sync_formats_for_row(alpha2, row)
    row["education_pack_tier"] = _resolve_pack_tier(alpha2.upper())
    # Refresh customer risks
    risks = [r for r in (row.get("customer_risks") or []) if r != "skeleton_row_requires_dissection"]
    if row["education_pack_tier"] == "generic_fallback" and row.get("sovereign_state"):
        if "generic_pack_for_sovereign_state" not in risks:
            risks.append("generic_pack_for_sovereign_state")
    row["customer_risks"] = risks
    return passes_locale_quality_gate(row) and passes_governance_quality_gate(row)


_WAVE_CONTINENT = {
    "W-Africa": "africa",
    "W-Asia": "asia",
    "W-Europe": "europe",
    "W-Americas": "americas",
    "W-Oceania": "oceania",
    "W-Territories": "territories",
}


def _continent_filter(continent_arg: str, row: dict[str, Any]) -> bool:
    if continent_arg == "all":
        return True
    continent = str(row.get("continent") or "").lower()
    wave = str(row.get("dissection_wave") or "").lower()
    arg = continent_arg.lower()
    if arg in ("territories", "territory"):
        return wave == "w-territories" or bool(row.get("territory"))
    if arg == "americas":
        return continent == "americas"
    if arg == "africa":
        return continent == "africa"
    return continent == arg.lower()


def write_shards(matrix: dict[str, Any]) -> int:
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    for row in matrix["rows"]:
        iso = row["iso_alpha2"]
        path = SHARD_DIR / f"{iso}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(matrix["rows"])


def sync_ledger(matrix: dict[str, Any]) -> dict[str, Any]:
    if not LEDGER_PATH.is_file():
        return {}
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    row_by_iso = {str(r["iso_alpha2"]): r for r in matrix["rows"]}
    now = datetime.now(timezone.utc).isoformat()
    for entry in ledger.get("entries") or []:
        iso = str(entry.get("iso_alpha2") or "")
        row = row_by_iso.get(iso)
        if not row:
            continue
        status = str(row.get("dissection_status") or "skeleton")
        entry["dissection_status"] = status
        if status == "verified":
            entry["verified_at"] = entry.get("verified_at") or now
    ledger["verified_count"] = sum(
        1 for e in ledger.get("entries") or [] if e.get("dissection_status") == "verified"
    )
    ledger["generated_at"] = now
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich country governance matrix (Phase 0C locale pass)")
    parser.add_argument(
        "--continent",
        default="all",
        help="Continent filter: all | africa | asia | europe | americas | oceania | territories",
    )
    parser.add_argument(
        "--wave",
        default=None,
        help="Dissection wave alias (e.g. W-Africa maps to continent africa)",
    )
    parser.add_argument("--write", action="store_true", help="Write matrix, shards, and ledger")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    if not MATRIX_PATH.is_file():
        print("FAIL: country_governance_matrix.json missing — run generate_global_governance_bootstrap.py first", file=sys.stderr)
        return 1

    _bootstrap_django()
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = matrix.get("rows") or []
    now = datetime.now(timezone.utc).isoformat()

    continent_filter = args.continent
    if args.wave and args.wave in _WAVE_CONTINENT:
        continent_filter = _WAVE_CONTINENT[args.wave]

    enriched = 0
    verified = 0
    africa_verified = 0
    failed: list[str] = []

    for row in rows:
        iso = str(row.get("iso_alpha2") or "").upper()
        if not _continent_filter(continent_filter, row):
            continue
        prior_status = str(row.get("dissection_status") or "")
        ok = enrich_row(iso, row)
        enriched += 1
        if ok or prior_status == "verified":
            row["dissection_status"] = "verified"
            verified += 1
            if str(row.get("continent") or "") == "Africa":
                africa_verified += 1
        else:
            row["dissection_status"] = "languages"
            failed.append(iso)

    matrix["generated_at"] = now
    total_verified = sum(1 for r in rows if r.get("dissection_status") == "verified")
    africa_total = sum(1 for r in rows if r.get("continent") == "Africa")

    print(f"Continent filter: {continent_filter}" + (f" (wave {args.wave})" if args.wave else ""))
    print(f"Rows enriched: {enriched}")
    print(f"Rows verified this pass: {verified}")
    print(f"African rows verified: {africa_verified}/{africa_total}")
    print(f"Total verified in matrix: {total_verified}/{len(rows)}")
    if failed:
        print(f"Quality gate misses ({len(failed)}): {', '.join(failed[:15])}" + (
            f" (+{len(failed) - 15} more)" if len(failed) > 15 else ""
        ))

    if args.write and not args.dry_run:
        MATRIX_PATH.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shard_count = write_shards(matrix)
        ledger = sync_ledger(matrix)
        if ledger:
            LEDGER_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote matrix, {shard_count} shards, ledger (verified_count={ledger.get('verified_count', '?')})")

    return 0 if verified == enriched else 1


if __name__ == "__main__":
    raise SystemExit(main())
