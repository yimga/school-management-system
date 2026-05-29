"""Per-country governance overrides for African ISO codes (Phase 0C W-Africa wave)."""

from __future__ import annotations

from typing import Any


def _levels(*pairs: tuple[str, dict[str, str]]) -> list[dict[str, Any]]:
    return [{"level": idx + 1, "label_en": en, "label_local": loc} for idx, (en, loc) in enumerate(pairs)]


def _fr_hub(
    ministry_fr: str,
    *,
    region_fr: str = "Région",
    dept_fr: str = "Département",
    employer: str = "state",
    mode: str = "group_common",
) -> dict[str, Any]:
    return {
        "governance_archetype": "state_emis_hub",
        "admin_levels": _levels(
            ("National ministry", {"fr": ministry_fr}),
            ("Region", {"fr": region_fr}),
            (dept_fr.title() if dept_fr[0].isupper() else "Department", {"fr": dept_fr}),
            ("School", {"fr": "Établissement scolaire"}),
        ),
        "employer_model": employer,
        "reporting_chain": ["school", "department", "region", "ministry"],
        "recommended_operating_mode": mode,
    }


def _en_district(
    ministry_en: str,
    *,
    district_en: str = "District",
    province_en: str | None = None,
    employer: str = "district",
    mode: str = "group_common",
) -> dict[str, Any]:
    levels: list[tuple[str, dict[str, str]]] = [
        ("National ministry", {"en": ministry_en}),
    ]
    if province_en:
        levels.append((province_en, {"en": province_en}))
    levels.append((district_en, {"en": district_en}))
    levels.append(("School", {"en": "School"}))
    chain = ["school", "district"]
    if province_en:
        chain.insert(1, province_en.lower().replace(" ", "_"))
    chain.append("ministry")
    return {
        "governance_archetype": "district_trust_overlay",
        "admin_levels": _levels(*levels),
        "employer_model": employer,
        "reporting_chain": chain,
        "recommended_operating_mode": mode,
    }


def _pt_hub(ministry_pt: str, *, employer: str = "state") -> dict[str, Any]:
    return {
        "governance_archetype": "state_emis_hub",
        "admin_levels": _levels(
            ("National ministry", {"pt": ministry_pt}),
            ("Province", {"pt": "Província"}),
            ("Municipality", {"pt": "Município"}),
            ("School", {"pt": "Escola"}),
        ),
        "employer_model": employer,
        "reporting_chain": ["school", "municipality", "province", "ministry"],
        "recommended_operating_mode": "group_common",
    }


def _ar_hub(
    ministry_ar: str,
    *,
    ministry_fr: str | None = None,
    province_ar: str = "ولاية",
    employer: str = "state",
) -> dict[str, Any]:
    loc: dict[str, str] = {"ar": ministry_ar}
    if ministry_fr:
        loc["fr"] = ministry_fr
    return {
        "governance_archetype": "state_emis_hub",
        "admin_levels": _levels(
            ("National ministry", loc),
            ("Province / Wilaya", {"ar": province_ar, **({"fr": "Wilaya"} if ministry_fr else {})}),
            ("District", {"ar": "دائرة", **({"fr": "Daïra"} if ministry_fr else {})}),
            ("School", {"ar": "مدرسة", **({"fr": "Établissement"} if ministry_fr else {})}),
        ),
        "employer_model": employer,
        "reporting_chain": ["school", "district", "province", "ministry"],
        "recommended_operating_mode": "group_common",
    }


def _federal_anglophone(
    ministry_en: str,
    *,
    state_label: str = "State",
    lga_label: str = "LGA",
) -> dict[str, Any]:
    return {
        "governance_archetype": "federation_equals",
        "admin_levels": _levels(
            ("Federal ministry", {"en": ministry_en}),
            (state_label, {"en": state_label}),
            (lga_label, {"en": lga_label}),
            ("School", {"en": "School"}),
        ),
        "employer_model": "state",
        "reporting_chain": ["school", "lga", "state", "ministry"],
        "recommended_operating_mode": "group_with_local_sovereignty",
    }


def _small_state(
    ministry_en: str,
    *,
    ministry_local: dict[str, str] | None = None,
    employer: str = "state",
) -> dict[str, Any]:
    loc = dict(ministry_local or {})
    if "en" not in loc:
        loc["en"] = ministry_en
    return {
        "governance_archetype": "single_org_multi_site",
        "admin_levels": _levels(
            ("National ministry", loc),
            ("School", {"en": "School", **{k: v for k, v in loc.items() if k != "en"}}),
        ),
        "employer_model": employer,
        "reporting_chain": ["school", "ministry"],
        "recommended_operating_mode": "standalone",
    }


def _territory_inherit(
    parent_archetype: str,
    parent_ministry_en: str,
    *,
    parent_iso: str,
    employer: str = "state",
) -> dict[str, Any]:
    return {
        "governance_archetype": parent_archetype,
        "admin_levels": _levels(
            ("Territory administration", {"en": f"Territory ({parent_iso})"}),
            ("School", {"en": "School"}),
        ),
        "employer_model": employer,
        "reporting_chain": ["school", "territory", "parent_sovereign"],
        "recommended_operating_mode": "standalone",
        "statutory_framework_ref": parent_iso,
        "customer_risks": [f"territory_inherits_{parent_iso}_governance"],
    }


# ---------------------------------------------------------------------------
# Tier-1 deep markets (hand-researched admin chains)
# ---------------------------------------------------------------------------

_T1: dict[str, dict[str, Any]] = {
    "CM": {
        **_federal_anglophone(
            "Ministry of Secondary Education / Ministère des Enseignements Secondaires",
            state_label="Region",
            lga_label="Division",
        ),
        "admin_levels": _levels(
            ("National ministry", {"en": "Ministry of Basic Education", "fr": "Ministère de l'Éducation de Base"}),
            ("Region", {"en": "Region", "fr": "Région"}),
            ("Division", {"en": "Division", "fr": "Département"}),
            ("Sub-division", {"en": "Sub-division", "fr": "Arrondissement"}),
            ("School", {"en": "School", "fr": "Établissement scolaire"}),
        ),
        "employer_model": "state",
        "ownership_types": ["public", "private", "faith", "international"],
        "school_structure": "both_common",
    },
    "NG": {
        **_federal_anglophone("Federal Ministry of Education"),
        "employer_model": "state",
        "ownership_types": ["public", "private", "faith", "international"],
        "school_structure": "both_common",
        "grading_scale_family": "WASSCE",
        "calendar_notes": "3 terms; federal structure with 36 states + FCT; UBEC/LGEA reporting.",
    },
    "KE": {
        **_en_district(
            "Ministry of Education",
            district_en="County",
            province_en="Sub-county",
            employer="state",
        ),
        "grading_scale_family": "KNEC",
        "calendar_notes": "3 terms; CBC rollout; county-level EMIS via NEMIS.",
    },
    "GH": {
        **_en_district("Ministry of Education", district_en="District", employer="district"),
        "grading_scale_family": "WASSCE",
        "calendar_notes": "3 terms; GES district oversight; SHS placement via CSSPS.",
    },
    "ZA": {
        "governance_archetype": "federation_equals",
        "admin_levels": _levels(
            ("National department", {"en": "Department of Basic Education", "af": "Departement van Basiese Onderwys"}),
            ("Province", {"en": "Province", "af": "Provinsie"}),
            ("District", {"en": "Education district", "af": "Onderwysdistrik"}),
            ("School", {"en": "School", "af": "Skool"}),
        ),
        "employer_model": "state",
        "reporting_chain": ["school", "district", "province", "ministry"],
        "recommended_operating_mode": "group_with_local_sovereignty",
        "ownership_types": ["public", "private", "independent", "faith"],
        "school_structure": "both_common",
        "grading_scale_family": "NSC",
    },
    "SN": _fr_hub("Ministère de l'Éducation Nationale"),
    "CI": _fr_hub("Ministère de l'Éducation Nationale et de l'Alphabétisation", region_fr="District autonome"),
    "TZ": {
        **_en_district(
            "Ministry of Education, Science and Technology",
            district_en="Council",
            province_en="Region",
            employer="state",
        ),
        "admin_levels": _levels(
            ("National ministry", {"en": "Ministry of Education", "sw": "Wizara ya Elimu"}),
            ("Region", {"en": "Region", "sw": "Mkoa"}),
            ("Council", {"en": "Council", "sw": "Halmashauri"}),
            ("Ward", {"en": "Ward", "sw": "Kata"}),
            ("School", {"en": "School", "sw": "Shule"}),
        ),
        "reporting_chain": ["school", "ward", "council", "region", "ministry"],
    },
    "UG": _en_district("Ministry of Education and Sports", district_en="District", employer="district"),
    "RW": _en_district("Ministry of Education", district_en="District", employer="state"),
    "ET": {
        "governance_archetype": "federation_equals",
        "admin_levels": _levels(
            ("Federal ministry", {"en": "Ministry of Education", "am": "የትምህርት ሚኒስቴር"}),
            ("Region", {"en": "Region", "am": "ክልል"}),
            ("Zone", {"en": "Zone", "am": "ዞን"}),
            ("Woreda", {"en": "Woreda", "am": "ወረዳ"}),
            ("School", {"en": "School", "am": "ትምህርት ቤት"}),
        ),
        "employer_model": "state",
        "reporting_chain": ["school", "woreda", "zone", "region", "ministry"],
        "recommended_operating_mode": "group_with_local_sovereignty",
    },
    "EG": _ar_hub("وزارة التربية والتعليم", ministry_fr="Ministère de l'Éducation"),
    "MA": _ar_hub(
        "وزارة التربية الوطنية والتعليم الأولي والرياضة",
        ministry_fr="Ministère de l'Éducation Nationale",
        province_ar="جهة",
    ),
    "DZ": _ar_hub(
        "وزارة التربية الوطنية",
        ministry_fr="Ministère de l'Éducation Nationale",
    ),
    "TN": _ar_hub(
        "وزارة التربية",
        ministry_fr="Ministère de l'Éducation",
    ),
}

# ---------------------------------------------------------------------------
# Francophone West & Central Africa
# ---------------------------------------------------------------------------

_FR_WEST = {
    "BJ": _fr_hub("Ministère des Enseignements Maternel et Primaire"),
    "BF": _fr_hub("Ministère de l'Éducation Nationale et de l'Alphabétisation"),
    "ML": _fr_hub("Ministère de l'Éducation Nationale"),
    "NE": _fr_hub("Ministère de l'Éducation Nationale"),
    "TG": _fr_hub("Ministère de l'Éducation Nationale"),
    "GN": _fr_hub("Ministère de l'Éducation Nationale et de l'Alphabétisation"),
    "GA": _fr_hub("Ministère de l'Éducation Nationale"),
    "CG": _fr_hub("Ministère de l'Enseignement Pré-universitaire"),
    "CD": _fr_hub("Ministère de l'Enseignement Primaire, Secondaire et Technique"),
    "CF": _fr_hub("Ministère de l'Éducation Nationale"),
    "TD": _fr_hub("Ministère de l'Éducation Nationale", region_fr="Province"),
    "GQ": {
        **_fr_hub("Ministère de l'Éducation"),
        "admin_levels": _levels(
            ("National ministry", {"es": "Ministerio de Educación", "fr": "Ministère de l'Éducation"}),
            ("Province", {"es": "Provincia", "fr": "Province"}),
            ("District", {"es": "Distrito", "fr": "District"}),
            ("School", {"es": "Escuela", "fr": "École"}),
        ),
    },
    "MG": _fr_hub("Ministère de l'Éducation Nationale", region_fr="Région", dept_fr="District"),
}

# ---------------------------------------------------------------------------
# Anglophone West & East Africa
# ---------------------------------------------------------------------------

_EN_WEST_EAST = {
    "SL": _en_district("Ministry of Basic and Senior Secondary Education", district_en="District"),
    "LR": _en_district("Ministry of Education", district_en="District"),
    "GM": _small_state("Ministry of Basic and Secondary Education"),
    "MW": _en_district("Ministry of Education", district_en="District"),
    "ZM": _en_district("Ministry of Education", district_en="District", province_en="Province"),
    "ZW": _en_district("Ministry of Primary and Secondary Education", district_en="District", province_en="Province"),
    "BW": _en_district("Ministry of Education and Skills Development", district_en="District"),
    "NA": _en_district("Ministry of Education, Arts and Culture", district_en="Region", province_en="Region"),
    "LS": _small_state("Ministry of Education and Training", ministry_local={"en": "Ministry of Education", "st": "Lefapha la Thuto"}),
    "SZ": _small_state("Ministry of Education and Training"),
    "SS": _en_district("Ministry of General Education and Instruction", district_en="County", province_en="State"),
    "SD": _ar_hub("وزارة التربية والتعليم", ministry_fr="Ministère de l'Éducation"),
    "SO": {
        **_en_district("Ministry of Education, Culture and Higher Education", district_en="District", province_en="State"),
        "admin_levels": _levels(
            ("National ministry", {"so": "Wasaaradda Waxbarashada", "ar": "وزارة التربية", "en": "Ministry of Education"}),
            ("Federal member state", {"en": "Federal Member State"}),
            ("District", {"en": "District", "so": "Degmo"}),
            ("School", {"en": "School", "so": "Dugsi"}),
        ),
    },
    "ER": {
        "governance_archetype": "state_emis_hub",
        "admin_levels": _levels(
            ("National ministry", {"en": "Ministry of Education", "ti": "ሚኒስትሪ ትምህርቲ"}),
            ("Region", {"en": "Region", "ti": "ዞባ"}),
            ("Sub-region", {"en": "Sub-region", "ti": "ንኡስ ዞባ"}),
            ("School", {"en": "School", "ti": "ቤት ትምህርቲ"}),
        ),
        "employer_model": "state",
        "reporting_chain": ["school", "sub_region", "region", "ministry"],
        "recommended_operating_mode": "group_common",
    },
    "BI": _fr_hub("Ministère de l'Éducation Nationale et de la Recherche Scientifique"),
    "SC": _small_state(
        "Ministry of Education",
        ministry_local={"en": "Ministry of Education", "fr": "Ministère de l'Éducation"},
    ),
    "MU": _small_state(
        "Ministry of Education, Tertiary Education, Science and Technology",
        ministry_local={"en": "Ministry of Education", "fr": "Ministère de l'Éducation"},
    ),
    "KM": _small_state("Ministère de l'Éducation Nationale", ministry_local={"fr": "Ministère de l'Éducation Nationale"}),
}

# ---------------------------------------------------------------------------
# Lusophone Africa
# ---------------------------------------------------------------------------

_PT = {
    "AO": _pt_hub("Ministério da Educação"),
    "MZ": _pt_hub("Ministério da Educação e Desenvolvimento Humano"),
    "CV": _small_state("Ministério da Educação", ministry_local={"pt": "Ministério da Educação"}),
    "GW": _small_state("Ministério da Educação", ministry_local={"pt": "Ministério da Educação"}),
    "ST": _small_state("Ministério da Educação", ministry_local={"pt": "Ministério da Educação"}),
}

# ---------------------------------------------------------------------------
# Arabic North & hybrid
# ---------------------------------------------------------------------------

_AR = {
    "LY": _ar_hub("وزارة التربية والتعليم"),
    "MR": _ar_hub("وزارة التربية", ministry_fr="Ministère de l'Éducation Nationale"),
    "DJ": _small_state(
        "Ministère de l'Éducation Nationale",
        ministry_local={"fr": "Ministère de l'Éducation Nationale", "ar": "وزارة التربية"},
    ),
}

# ---------------------------------------------------------------------------
# Territories (T3 — inherit parent sovereign patterns)
# ---------------------------------------------------------------------------

_TERRITORIES: dict[str, dict[str, Any]] = {
    "EH": _territory_inherit("state_emis_hub", "Morocco Ministry of Education", parent_iso="MA"),
    "RE": _territory_inherit("state_emis_hub", "French Ministry of Education", parent_iso="FR"),
    "YT": _territory_inherit("state_emis_hub", "French Ministry of Education", parent_iso="FR"),
    "TF": _territory_inherit("state_emis_hub", "French Ministry of Education", parent_iso="FR"),
    "SH": _territory_inherit("district_trust_overlay", "UK Department for Education", parent_iso="GB"),
}

# Faith / proprietor overlays (employer_model hints for mixed systems)
_FAITH_NGO_HINTS: dict[str, dict[str, Any]] = {
    "NG": {"ownership_types": ["public", "private", "faith", "international", "ngo"]},
    "KE": {"ownership_types": ["public", "private", "faith", "ngo"]},
    "GH": {"ownership_types": ["public", "private", "faith", "ngo"]},
    "UG": {"ownership_types": ["public", "private", "faith", "ngo"]},
    "RW": {"ownership_types": ["public", "private", "faith", "ngo"]},
    "SN": {"ownership_types": ["public", "private", "faith", "ngo"], "employer_model": "state"},
    "CI": {"ownership_types": ["public", "private", "faith", "ngo"]},
    "CM": {"ownership_types": ["public", "private", "faith", "international", "ngo"]},
}


def _merge(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if key in out and isinstance(out[key], dict) and isinstance(value, dict):
                merged = dict(out[key])
                merged.update(value)
                out[key] = merged
            elif key in out and isinstance(out[key], list) and isinstance(value, list):
                out[key] = value
            else:
                out[key] = value
    return out


def build_africa_override(alpha2: str) -> dict[str, Any] | None:
    """Return governance override dict for an African ISO code, or None."""
    code = (alpha2 or "").strip().upper()
    if code in _T1:
        base = dict(_T1[code])
    elif code in _FR_WEST:
        base = dict(_FR_WEST[code])
    elif code in _EN_WEST_EAST:
        base = dict(_EN_WEST_EAST[code])
    elif code in _PT:
        base = dict(_PT[code])
    elif code in _AR:
        base = dict(_AR[code])
    elif code in _TERRITORIES:
        base = dict(_TERRITORIES[code])
    else:
        return None
    if code in _FAITH_NGO_HINTS:
        base = _merge(base, _FAITH_NGO_HINTS[code])
    return base


AFRICA_GOVERNANCE_OVERRIDES: dict[str, dict[str, Any]] = {
    code: override
    for code in sorted(
        set(_T1)
        | set(_FR_WEST)
        | set(_EN_WEST_EAST)
        | set(_PT)
        | set(_AR)
        | set(_TERRITORIES)
    )
    if (override := build_africa_override(code)) is not None
}
