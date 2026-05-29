"""Country- and system-type-aware grading bands. v4.00.30 (2026-05-29).

Keyed by the EducationSystemTypeRegistry codes seeded from the country packs
in _seed_country_localization.py. Reference data, not tenant state — so we
keep it in code rather than DB. Selectors below let resolvers / wizards /
gradebook UIs pick the right default scale for a school based on its
multi-selected system types and country code.

Each entry: {
  "code":  short slug,
  "label": display label,
  "scale_type": "percent" | "letter" | "gpa" | "points_n" | "competency",
  "max":   numeric ceiling where applicable,
  "pass":  pass cutoff,
  "bands": [{"min": int, "max": int, "label": str}],
}
"""
from __future__ import annotations

from typing import Any


# Per-system-type defaults. Keys match codes used in COUNTRY_LOCALIZATION
# school_types lists. If a system type has no entry, fall back to country-level.
SYSTEM_TYPE_BANDS: dict[str, dict[str, Any]] = {
    # Cameroon — Francophone (note 20)
    "lycee": {
        "code": "cm-note-20", "label": "Note sur 20 (Francophone)",
        "scale_type": "points_n", "max": 20, "pass": 10,
        "bands": [
            {"min": 16, "max": 20, "label": "Très bien"},
            {"min": 14, "max": 15, "label": "Bien"},
            {"min": 12, "max": 13, "label": "Assez bien"},
            {"min": 10, "max": 11, "label": "Passable"},
            {"min": 0,  "max": 9,  "label": "Insuffisant"},
        ],
    },
    "college": {
        "code": "cm-note-20", "label": "Note sur 20 (Francophone)",
        "scale_type": "points_n", "max": 20, "pass": 10,
        "bands": [
            {"min": 16, "max": 20, "label": "Très bien"},
            {"min": 14, "max": 15, "label": "Bien"},
            {"min": 10, "max": 13, "label": "Passable"},
            {"min": 0,  "max": 9,  "label": "Insuffisant"},
        ],
    },
    # Cameroon — Anglophone (GCE letters)
    "secondary-anglo": {
        "code": "cm-gce", "label": "GCE Grade (A–F)",
        "scale_type": "letter", "max": None, "pass": "C",
        "bands": [
            {"min": "A1", "max": "A1", "label": "Distinction"},
            {"min": "B2", "max": "B3", "label": "Credit"},
            {"min": "C4", "max": "C6", "label": "Credit"},
            {"min": "D7", "max": "D7", "label": "Pass"},
            {"min": "E8", "max": "E8", "label": "Pass"},
            {"min": "F9", "max": "F9", "label": "Fail"},
        ],
    },
    # WAEC family — Ghana / Nigeria / Liberia / Gambia / Sierra Leone
    "shs": {
        "code": "waec-wassce", "label": "WASSCE (A1–F9)",
        "scale_type": "letter", "max": None, "pass": "C6",
        "bands": [
            {"min": "A1", "max": "A1", "label": "Excellent"},
            {"min": "B2", "max": "B2", "label": "Very Good"},
            {"min": "B3", "max": "B3", "label": "Good"},
            {"min": "C4", "max": "C6", "label": "Credit"},
            {"min": "D7", "max": "E8", "label": "Pass"},
            {"min": "F9", "max": "F9", "label": "Fail"},
        ],
    },
    "jhs": {
        "code": "waec-bece", "label": "BECE (1–9)",
        "scale_type": "letter", "max": None, "pass": 6,
        "bands": [
            {"min": 1, "max": 1, "label": "Highest"},
            {"min": 2, "max": 3, "label": "Higher"},
            {"min": 4, "max": 6, "label": "High Average"},
            {"min": 7, "max": 8, "label": "Low Average"},
            {"min": 9, "max": 9, "label": "Low"},
        ],
    },
    # Kenya CBC
    "junior-secondary": {
        "code": "ke-cbc", "label": "CBC Performance (4 levels)",
        "scale_type": "competency", "max": 4, "pass": 2,
        "bands": [
            {"min": 4, "max": 4, "label": "Exceeding Expectation"},
            {"min": 3, "max": 3, "label": "Meeting Expectation"},
            {"min": 2, "max": 2, "label": "Approaching Expectation"},
            {"min": 1, "max": 1, "label": "Below Expectation"},
        ],
    },
    "senior-school": {
        "code": "ke-kcse", "label": "KCSE Grade (A–E)",
        "scale_type": "letter", "max": None, "pass": "D",
        "bands": [
            {"min": "A",  "max": "A",  "label": "Excellent"},
            {"min": "A-", "max": "B+", "label": "Very Good"},
            {"min": "B",  "max": "C+", "label": "Good"},
            {"min": "C",  "max": "C-", "label": "Average"},
            {"min": "D+", "max": "D-", "label": "Below Average"},
            {"min": "E",  "max": "E",  "label": "Fail"},
        ],
    },
    # Rwanda
    "rw-secondaire": {
        "code": "rw-percent", "label": "Pourcentage (Rwanda)",
        "scale_type": "percent", "max": 100, "pass": 50,
        "bands": [
            {"min": 80, "max": 100, "label": "Distinction"},
            {"min": 70, "max": 79,  "label": "Très bien"},
            {"min": 60, "max": 69,  "label": "Bien"},
            {"min": 50, "max": 59,  "label": "Assez bien"},
            {"min": 0,  "max": 49,  "label": "Échec"},
        ],
    },
    # Senegal / Côte d'Ivoire — Francophone note-20
    "lycee-sn": {
        "code": "sn-note-20", "label": "Note sur 20 (Sénégal)",
        "scale_type": "points_n", "max": 20, "pass": 10,
        "bands": [
            {"min": 16, "max": 20, "label": "Très bien"},
            {"min": 14, "max": 15, "label": "Bien"},
            {"min": 12, "max": 13, "label": "Assez bien"},
            {"min": 10, "max": 11, "label": "Passable"},
            {"min": 0,  "max": 9,  "label": "Insuffisant"},
        ],
    },
    # Tanzania — letters A–F
    "sekondari-o": {
        "code": "tz-csee", "label": "CSEE Division (A–F)",
        "scale_type": "letter", "max": None, "pass": "C",
        "bands": [
            {"min": "A", "max": "A", "label": "Excellent"},
            {"min": "B+","max": "B", "label": "Very Good"},
            {"min": "C", "max": "C", "label": "Good"},
            {"min": "D", "max": "D", "label": "Satisfactory"},
            {"min": "F", "max": "F", "label": "Fail"},
        ],
    },
    "sekondari-a": {
        "code": "tz-acsee", "label": "ACSEE Division (A–F)",
        "scale_type": "letter", "max": None, "pass": "S",
        "bands": [
            {"min": "A", "max": "A", "label": "Excellent"},
            {"min": "B", "max": "B", "label": "Very Good"},
            {"min": "C", "max": "C", "label": "Good"},
            {"min": "D", "max": "D", "label": "Satisfactory"},
            {"min": "S", "max": "S", "label": "Subsidiary"},
            {"min": "F", "max": "F", "label": "Fail"},
        ],
    },
    # Uganda — UCE/UACE letters
    "o-level": {
        "code": "ug-uce", "label": "UCE Grade (D1–F9)",
        "scale_type": "letter", "max": None, "pass": "C6",
        "bands": [
            {"min": "D1", "max": "D2", "label": "Distinction"},
            {"min": "C3", "max": "C6", "label": "Credit"},
            {"min": "P7", "max": "P8", "label": "Pass"},
            {"min": "F9", "max": "F9", "label": "Fail"},
        ],
    },
    # Ethiopia — percent grade
    "preparatory": {
        "code": "et-percent", "label": "Percent (EHEECE prep)",
        "scale_type": "percent", "max": 100, "pass": 50,
        "bands": [
            {"min": 90, "max": 100, "label": "A"},
            {"min": 80, "max": 89,  "label": "B+"},
            {"min": 70, "max": 79,  "label": "B"},
            {"min": 60, "max": 69,  "label": "C+"},
            {"min": 50, "max": 59,  "label": "C"},
            {"min": 0,  "max": 49,  "label": "F"},
        ],
    },
    # Egypt — Thanaweya Amma percent (50% pass; uni cutoff much higher)
    "secondary-general": {
        "code": "eg-thanaweya", "label": "Thanaweya Amma (%)",
        "scale_type": "percent", "max": 100, "pass": 50,
        "bands": [
            {"min": 95, "max": 100, "label": "ممتاز / Excellent"},
            {"min": 85, "max": 94,  "label": "جيد جدا / Very Good"},
            {"min": 75, "max": 84,  "label": "جيد / Good"},
            {"min": 65, "max": 74,  "label": "مقبول / Acceptable"},
            {"min": 50, "max": 64,  "label": "ضعيف / Weak Pass"},
            {"min": 0,  "max": 49,  "label": "راسب / Fail"},
        ],
    },
    # South Africa — NSC bands (7-level)
    "fet": {
        "code": "za-nsc", "label": "NSC 7-level (Matric)",
        "scale_type": "percent", "max": 100, "pass": 30,
        "bands": [
            {"min": 80, "max": 100, "label": "Level 7 — Outstanding"},
            {"min": 70, "max": 79,  "label": "Level 6 — Meritorious"},
            {"min": 60, "max": 69,  "label": "Level 5 — Substantial"},
            {"min": 50, "max": 59,  "label": "Level 4 — Adequate"},
            {"min": 40, "max": 49,  "label": "Level 3 — Moderate"},
            {"min": 30, "max": 39,  "label": "Level 2 — Elementary"},
            {"min": 0,  "max": 29,  "label": "Level 1 — Not Achieved"},
        ],
    },
}


# Country-level fallback when no system-type match exists yet.
COUNTRY_DEFAULT_BAND: dict[str, str] = {
    "CM": "cm-note-20",  "SN": "sn-note-20",   "CI": "sn-note-20",
    "GH": "waec-wassce", "NG": "waec-wassce",  "LR": "waec-wassce",
    "GM": "waec-wassce", "SL": "waec-wassce",
    "KE": "ke-kcse",     "RW": "rw-percent",
    "TZ": "tz-csee",     "UG": "ug-uce",
    "ET": "et-percent",  "EG": "eg-thanaweya",
    "ZA": "za-nsc",
}


# Generic universal scales — always offered, but not always the default.
UNIVERSAL_SCALES: list[dict[str, Any]] = [
    {"code": "percent_100", "label": "Percentage 0–100", "scale_type": "percent",
     "max": 100, "pass": 50,
     "bands": [
         {"min": 90, "max": 100, "label": "A"},
         {"min": 80, "max": 89,  "label": "B"},
         {"min": 70, "max": 79,  "label": "C"},
         {"min": 60, "max": 69,  "label": "D"},
         {"min": 0,  "max": 59,  "label": "F"},
     ]},
    {"code": "letter_a_f", "label": "Letter A–F", "scale_type": "letter",
     "max": None, "pass": "D",
     "bands": [
         {"min": "A", "max": "A", "label": "Excellent"},
         {"min": "B", "max": "B", "label": "Good"},
         {"min": "C", "max": "C", "label": "Average"},
         {"min": "D", "max": "D", "label": "Below Average"},
         {"min": "F", "max": "F", "label": "Fail"},
     ]},
    {"code": "gpa_4",    "label": "GPA 0.0–4.0", "scale_type": "gpa",
     "max": 4.0, "pass": 2.0, "bands": []},
    {"code": "points_20","label": "Points out of 20 (Francophone)", "scale_type": "points_n",
     "max": 20, "pass": 10, "bands": []},
    {"code": "competency_pass_fail", "label": "Competency Pass/Fail",
     "scale_type": "competency", "max": None, "pass": None, "bands": []},
]


def bands_for_school(*, country_code: str = "", system_type_codes: list[str] | None = None) -> dict[str, Any] | None:
    """Return the best-matching grading band for a school.

    Priority:
      1. First system-type code that has an explicit entry.
      2. Country-level fallback.
      3. None (caller falls back to generic percent_100).
    """
    for stc in (system_type_codes or []):
        if stc in SYSTEM_TYPE_BANDS:
            return SYSTEM_TYPE_BANDS[stc]
    cc = (country_code or "").upper()
    default_code = COUNTRY_DEFAULT_BAND.get(cc)
    if default_code:
        for band in SYSTEM_TYPE_BANDS.values():
            if band["code"] == default_code:
                return band
    return None


def grading_scale_choices(*, country_code: str = "", system_type_codes: list[str] | None = None) -> list[dict[str, Any]]:
    """Resolver-friendly choice list. Country-default first, then universals."""
    preferred = bands_for_school(country_code=country_code, system_type_codes=system_type_codes)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if preferred:
        out.append({
            "value": preferred["code"],
            "label_token": f"{preferred['label']} (recommended)",
            "metadata": {
                "scale_type": preferred["scale_type"],
                "max": preferred["max"], "pass": preferred["pass"],
                "country_default": True,
            },
        })
        seen.add(preferred["code"])
    for s in UNIVERSAL_SCALES:
        if s["code"] in seen:
            continue
        out.append({
            "value": s["code"], "label_token": s["label"],
            "metadata": {"scale_type": s["scale_type"], "max": s["max"], "pass": s["pass"]},
        })
        seen.add(s["code"])
    return out
