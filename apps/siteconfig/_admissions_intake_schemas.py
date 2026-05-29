"""Country- and system-type-aware admissions intake form schemas. v4.00.31.

Each schema describes the exam-score fields a school in that country/system
should collect when accepting a new applicant. Driven by the same
EducationSystemTypeRegistry codes seeded from _seed_country_localization.

Schema shape:
    {
        "code": short slug,
        "label": display label,
        "applies_to_level": "secondary" | "primary" | "middle" | "any",
        "exam_marker": e.g. "WASSCE" or "Thanaweya Amma",
        "subjects": [list of required subject codes],
        "score_kind": "letter" | "percent" | "points_20" | "competency",
        "min_subjects_required": int,
        "notes": one-line operator note,
    }

Resolver-friendly helpers:
    - intake_schema_for_school(country, system_codes) -> Schema | None
    - applicant_field_specs(schema) -> list of {name, label, type, choices}

The point: when a Ghanaian SHS sets up admissions, the form asks for WASSCE
core 4 + electives 4 with A1-F9 dropdowns — never a generic percent box that
admissions staff have to translate themselves.
"""
from __future__ import annotations

from typing import Any


WAEC_LETTERS = ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"]
UCE_LETTERS = ["D1", "D2", "C3", "C4", "C5", "C6", "P7", "P8", "F9"]
UACE_LETTERS = ["A", "B", "C", "D", "E", "O", "F"]
GCE_AL_LETTERS = ["A", "B", "C", "D", "E", "U"]
KCSE_LETTERS = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "E"]
CSEE_LETTERS = ["A", "B+", "B", "C", "D", "F"]
ACSEE_LETTERS = ["A", "B", "C", "D", "S", "F"]
NSC_LEVELS = ["Level 7", "Level 6", "Level 5", "Level 4", "Level 3", "Level 2", "Level 1"]
SA_NSC_PERCENT = [str(i) for i in range(0, 101, 10)]


SCHEMAS: dict[str, dict[str, Any]] = {
    # WAEC family — Ghana / Nigeria / Liberia / Sierra Leone / Gambia
    "waec-wassce": {
        "code": "waec-wassce", "label": "WASSCE (4 core + 4 elective)",
        "applies_to_level": "secondary", "exam_marker": "WASSCE",
        "subjects": [
            "english", "mathematics", "integrated_science", "social_studies",
            "elective_1", "elective_2", "elective_3", "elective_4",
        ],
        "score_kind": "letter", "choices": WAEC_LETTERS,
        "min_subjects_required": 6,
        "notes": "Aggregate of best 6 (4 core + 2 best electives) is the standard admission proxy.",
    },
    "waec-bece": {
        "code": "waec-bece", "label": "BECE (Ghana Basic 6+2 subjects)",
        "applies_to_level": "middle", "exam_marker": "BECE",
        "subjects": [
            "english", "mathematics", "integrated_science", "social_studies",
            "ghanaian_language", "religious_moral", "creative_arts", "ict",
        ],
        "score_kind": "letter", "choices": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
        "min_subjects_required": 6,
        "notes": "Aggregate is sum of best 6 grades — LOWER aggregate = better.",
    },
    # Cameroon Anglophone — GCE O-Level + A-Level
    "cm-gce-ol": {
        "code": "cm-gce-ol", "label": "GCE Ordinary Level (Cameroon)",
        "applies_to_level": "secondary", "exam_marker": "GCE O/L",
        "subjects": ["english", "mathematics", "french", "biology", "chemistry", "physics", "history"],
        "score_kind": "letter", "choices": ["A", "B", "C", "D", "E", "U"],
        "min_subjects_required": 5,
        "notes": "Minimum 5 subjects including English at C or better is standard A-Level entry.",
    },
    "cm-gce-al": {
        "code": "cm-gce-al", "label": "GCE Advanced Level (Cameroon)",
        "applies_to_level": "secondary", "exam_marker": "GCE A/L",
        "subjects": ["paper_1", "paper_2", "paper_3", "general_paper"],
        "score_kind": "letter", "choices": GCE_AL_LETTERS,
        "min_subjects_required": 3,
        "notes": "3 A-Level papers + General Paper. Min 2 at C or better for university.",
    },
    # Cameroon Francophone — BEPC + Probatoire + Baccalauréat
    "cm-bac": {
        "code": "cm-bac", "label": "Baccalauréat (Cameroun Francophone)",
        "applies_to_level": "secondary", "exam_marker": "Baccalauréat",
        "subjects": ["mathematiques", "francais", "philosophie", "sciences", "histoire_geo", "langue_vivante"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 5,
        "notes": "Notes sur 20. Moyenne ≥ 10/20 pour l'admission.",
    },
    "cm-bepc": {
        "code": "cm-bepc", "label": "BEPC (Cameroun Francophone)",
        "applies_to_level": "middle", "exam_marker": "BEPC",
        "subjects": ["mathematiques", "francais", "anglais", "histoire_geo", "svt", "education_civique"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 5,
        "notes": "Notes sur 20.",
    },
    # Kenya
    "ke-cbc": {
        "code": "ke-cbc", "label": "Kenya CBC Performance (4 levels)",
        "applies_to_level": "primary", "exam_marker": "KPSEA",
        "subjects": [
            "english", "kiswahili", "mathematics", "science_tech",
            "social_studies", "creative_arts", "religious_education", "agriculture",
        ],
        "score_kind": "competency", "choices": ["4 EE", "3 ME", "2 AE", "1 BE"],
        "min_subjects_required": 8,
        "notes": "Levels: 4 Exceeding / 3 Meeting / 2 Approaching / 1 Below.",
    },
    "ke-kcse": {
        "code": "ke-kcse", "label": "KCSE Grade (Kenya 8-4-4 / Senior School)",
        "applies_to_level": "secondary", "exam_marker": "KCSE",
        "subjects": ["english", "kiswahili", "mathematics", "biology", "chemistry", "physics", "geography", "history"],
        "score_kind": "letter", "choices": KCSE_LETTERS,
        "min_subjects_required": 7,
        "notes": "Mean grade C+ minimum for direct university entry.",
    },
    # Tanzania
    "tz-csee": {
        "code": "tz-csee", "label": "CSEE Division (Tanzania Form 4)",
        "applies_to_level": "secondary", "exam_marker": "CSEE",
        "subjects": ["english", "kiswahili", "mathematics", "biology", "chemistry", "physics", "geography", "history"],
        "score_kind": "letter", "choices": CSEE_LETTERS,
        "min_subjects_required": 7,
        "notes": "Division I-IV computed from best 7 subjects; Div I/II/III qualify for Form 5.",
    },
    "tz-acsee": {
        "code": "tz-acsee", "label": "ACSEE Division (Tanzania Form 6)",
        "applies_to_level": "secondary", "exam_marker": "ACSEE",
        "subjects": ["paper_1_principal", "paper_2_principal", "paper_3_principal", "general_studies"],
        "score_kind": "letter", "choices": ACSEE_LETTERS,
        "min_subjects_required": 3,
        "notes": "3 principal subjects + General Studies + Subsidiary credit.",
    },
    # Uganda
    "ug-uce": {
        "code": "ug-uce", "label": "UCE (Uganda S4)",
        "applies_to_level": "secondary", "exam_marker": "UCE",
        "subjects": ["english", "mathematics", "biology", "chemistry", "physics", "geography", "history"],
        "score_kind": "letter", "choices": UCE_LETTERS,
        "min_subjects_required": 8,
        "notes": "Lower aggregate = better. Aggregate 12 = First Grade.",
    },
    "ug-uace": {
        "code": "ug-uace", "label": "UACE (Uganda S6)",
        "applies_to_level": "secondary", "exam_marker": "UACE",
        "subjects": ["principal_1", "principal_2", "principal_3", "subsidiary_1", "general_paper"],
        "score_kind": "letter", "choices": UACE_LETTERS,
        "min_subjects_required": 5,
        "notes": "3 principals + 1 subsidiary + GP; weighted points map to university course.",
    },
    "ug-ple": {
        "code": "ug-ple", "label": "PLE (Uganda Primary)",
        "applies_to_level": "primary", "exam_marker": "PLE",
        "subjects": ["english", "mathematics", "social_studies", "integrated_science"],
        "score_kind": "letter", "choices": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
        "min_subjects_required": 4,
        "notes": "4-subject aggregate. Division I/II/III/IV/U computed from sum.",
    },
    # Ethiopia
    "et-egsece": {
        "code": "et-egsece", "label": "EGSECE (Ethiopia G10)",
        "applies_to_level": "secondary", "exam_marker": "EGSECE",
        "subjects": ["english", "mathematics", "biology", "chemistry", "physics", "civics", "amharic"],
        "score_kind": "percent", "choices": SA_NSC_PERCENT, "max": 100,
        "min_subjects_required": 7,
        "notes": "Pass 50% to advance to preparatory.",
    },
    "et-eheece": {
        "code": "et-eheece", "label": "EHEECE (Ethiopia G12)",
        "applies_to_level": "secondary", "exam_marker": "EHEECE",
        "subjects": ["english", "mathematics", "biology", "chemistry", "physics", "civics", "aptitude"],
        "score_kind": "percent", "choices": SA_NSC_PERCENT, "max": 100,
        "min_subjects_required": 7,
        "notes": "University placement threshold varies year-to-year by faculty.",
    },
    # Egypt
    "eg-thanaweya": {
        "code": "eg-thanaweya", "label": "Thanaweya Amma (Egypt Secondary 3)",
        "applies_to_level": "secondary", "exam_marker": "Thanaweya Amma",
        "subjects": [
            "arabic", "english", "second_language", "mathematics",
            "physics", "chemistry", "biology", "history_geography", "religion",
        ],
        "score_kind": "percent", "choices": SA_NSC_PERCENT, "max": 100,
        "min_subjects_required": 7,
        "notes": "Tansik (university placement) cutoffs are released annually by faculty.",
    },
    "eg-prep": {
        "code": "eg-prep", "label": "Preparatory Certificate (Egypt G9)",
        "applies_to_level": "middle", "exam_marker": "Preparatory Cert.",
        "subjects": ["arabic", "english", "mathematics", "science", "social_studies", "religion"],
        "score_kind": "percent", "choices": SA_NSC_PERCENT, "max": 100,
        "min_subjects_required": 6,
        "notes": "Required to advance to secondary general / Al-Azhar / technical track.",
    },
    # South Africa NSC
    "za-nsc": {
        "code": "za-nsc", "label": "NSC Matric (South Africa Grade 12)",
        "applies_to_level": "secondary", "exam_marker": "NSC Matric",
        "subjects": [
            "home_language", "first_additional_language", "mathematics_or_lit",
            "life_orientation", "elective_1", "elective_2", "elective_3",
        ],
        "score_kind": "level7", "choices": NSC_LEVELS,
        "min_subjects_required": 7,
        "notes": "Bachelor pass: 4 designated subjects at Level 4+; APS computed from best 6.",
    },
    # Senegal / Côte d'Ivoire / Togo / Benin / Burkina / Mali / Niger — Francophone Bac
    "fr-bac": {
        "code": "fr-bac", "label": "Baccalauréat (Francophone)",
        "applies_to_level": "secondary", "exam_marker": "Baccalauréat",
        "subjects": [
            "francais", "mathematiques", "philosophie", "histoire_geo",
            "sciences", "langue_vivante", "specialite_1", "specialite_2",
        ],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Note sur 20. Mention: AB (12), B (14), TB (16). Admis ≥ 10/20.",
    },
    "fr-bepc": {
        "code": "fr-bepc", "label": "BEPC / DEF / CFEPD (Francophone Middle)",
        "applies_to_level": "middle", "exam_marker": "BEPC / DEF / CFEPD",
        "subjects": ["francais", "mathematiques", "anglais", "histoire_geo", "svt", "pc"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 5,
        "notes": "Note sur 20.",
    },
    # Maghreb — Morocco/Tunisia/Algeria
    "ma-bac": {
        "code": "ma-bac", "label": "Baccalauréat (Maroc)",
        "applies_to_level": "secondary", "exam_marker": "Baccalauréat",
        "subjects": ["arabe", "francais", "anglais", "mathematiques", "sciences", "philosophie", "histoire_geo"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Note sur 20. Régional + National pondérés selon filière.",
    },
    "tn-bac": {
        "code": "tn-bac", "label": "Baccalauréat (Tunisie)",
        "applies_to_level": "secondary", "exam_marker": "Baccalauréat",
        "subjects": ["arabe", "francais", "anglais", "mathematiques", "sciences", "philosophie"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Note sur 20. Score d'orientation = moyenne pondérée par filière.",
    },
    "dz-bac": {
        "code": "dz-bac", "label": "Baccalauréat (Algérie)",
        "applies_to_level": "secondary", "exam_marker": "Baccalauréat",
        "subjects": ["arabe", "francais", "anglais", "mathematiques", "sciences", "philosophie", "histoire_geo"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Note sur 20. Admission university via la moyenne au Bac + filière.",
    },
    "dz-bem": {
        "code": "dz-bem", "label": "BEM (Algérie Brevet d'Enseignement Moyen)",
        "applies_to_level": "middle", "exam_marker": "BEM",
        "subjects": ["arabe", "francais", "mathematiques", "sciences", "histoire_geo", "education_islamique"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 5,
        "notes": "Note sur 20. Moyenne ≥ 10 pour passer au lycée.",
    },
    # Mozambique — Lusophone ESG-I + ESG-II.
    "mz-esg": {
        "code": "mz-esg", "label": "ESG-II (Moçambique Classe 12)",
        "applies_to_level": "secondary", "exam_marker": "Exame Nacional",
        "subjects": ["portugues", "ingles", "matematica", "fisica", "quimica", "biologia", "historia"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Notas 0-20. Aprovação: ≥10. Sistema de avaliação português adaptado.",
    },
    # Angola — Lusophone Médio (Classe 13).
    "ao-medio": {
        "code": "ao-medio", "label": "Médio (Angola Classe 13)",
        "applies_to_level": "secondary", "exam_marker": "Exame de Acesso",
        "subjects": ["portugues", "ingles", "matematica", "fisica", "quimica", "biologia", "historia"],
        "score_kind": "points_n", "choices": [str(i) for i in range(0, 21)], "max": 20,
        "min_subjects_required": 6,
        "notes": "Notas 0-20. Acesso ao ensino superior via exame nacional + média.",
    },
    # Rwanda
    "rw-percent": {
        "code": "rw-percent", "label": "Pourcentage (Rwanda)",
        "applies_to_level": "any", "exam_marker": "Rwanda National Exam",
        "subjects": ["english", "mathematics", "science", "history", "geography", "kinyarwanda", "french"],
        "score_kind": "percent", "choices": SA_NSC_PERCENT, "max": 100,
        "min_subjects_required": 5,
        "notes": "Pass = 50%. Distinction = 80%+.",
    },
}


# Maps system-type-code OR country-default → schema key. Mirrors the
# country-default fallback shape used in _grading_bands.py.
SYSTEM_TYPE_TO_SCHEMA: dict[str, str] = {
    # WAEC family
    "shs": "waec-wassce",
    "jhs": "waec-bece",
    # Cameroon
    "lycee": "cm-bac",
    "college": "cm-bepc",
    "secondary-anglo": "cm-gce-ol",
    # Kenya
    "senior-school": "ke-kcse",
    "junior-secondary": "ke-cbc",
    # Tanzania
    "sekondari-o": "tz-csee",
    "sekondari-a": "tz-acsee",
    # Uganda
    "o-level": "ug-uce",
    "a-level": "ug-uace",
    # Ethiopia
    "secondary-9-10": "et-egsece",
    "preparatory": "et-eheece",
    # Egypt
    "secondary-general": "eg-thanaweya",
    "secondary-azhar": "eg-thanaweya",
    "preparatory-eg": "eg-prep",
    # South Africa
    "fet": "za-nsc",
    # Maghreb
    "lycee-qualifiant": "ma-bac",
    "secondaire": "fr-bac",
    "moyen": "dz-bem",
    # Francophone fallback
    "lycee-sn": "fr-bac",
    # v4.00.32 — Anglo West Africa + Southern Africa + Lusophone:
    "senior-high": "waec-wassce",       # Liberia
    "senior-secondary": "waec-wassce",  # Gambia
    "sss": "waec-wassce",               # Sierra Leone
    "esg2": "mz-esg",                   # Mozambique
    "ii-ciclo-sec": "ao-medio",         # Angola
    # Madagascar lycée + Zimbabwe/Zambia inherit existing keys.
}


COUNTRY_DEFAULT_SCHEMA: dict[str, str] = {
    "CM": "cm-bac", "GH": "waec-wassce", "NG": "waec-wassce", "LR": "waec-wassce",
    "GM": "waec-wassce", "SL": "waec-wassce",
    "KE": "ke-kcse", "RW": "rw-percent",
    "TZ": "tz-csee", "UG": "ug-uce",
    "ET": "et-eheece", "EG": "eg-thanaweya",
    "ZA": "za-nsc",
    "SN": "fr-bac", "CI": "fr-bac", "TG": "fr-bac", "BJ": "fr-bac",
    "BF": "fr-bac", "ML": "fr-bac", "NE": "fr-bac",
    "MA": "ma-bac", "TN": "tn-bac", "DZ": "dz-bac",
    # v4.00.32 additions:
    "ZW": "za-nsc",  # ZIMSEC O/A — best-fit pre-dedicated-schema is NSC bands
    "ZM": "za-nsc",  # ECZ Grade 12 — same school-cert ladder
    "MZ": "mz-esg",  # Mozambique Lusophone ESG
    "AO": "ao-medio",  # Angola Lusophone Médio
    "MG": "fr-bac",
    # v4.00.33 additions:
    "SO": "ke-kcse",  # SSCE — letter-based, best-fit Kenya KCSE pattern
    "ER": "ke-kcse",  # ESECE — English-language letter
    "DJ": "fr-bac",   # French Bac
    "SS": "ke-kcse",  # CSE — letter
    "MW": "za-nsc",   # MSCE — credit/distinction
    "BW": "za-nsc",   # BGCSE — credit ladder
    "NA": "za-nsc",   # NSSCO/NSSCAS — Cambridge-style
    "LS": "za-nsc",   # LGCSE — Cambridge IGCSE
    "SZ": "za-nsc",   # EGCSE — Cambridge IGCSE
}


def intake_schema_for_school(*, country_code: str = "", system_type_codes: list[str] | None = None) -> dict[str, Any] | None:
    """Resolve the most-specific intake schema for a school."""
    for stc in (system_type_codes or []):
        key = SYSTEM_TYPE_TO_SCHEMA.get(stc)
        if key and key in SCHEMAS:
            return SCHEMAS[key]
    cc = (country_code or "").upper()
    default_key = COUNTRY_DEFAULT_SCHEMA.get(cc)
    if default_key and default_key in SCHEMAS:
        return SCHEMAS[default_key]
    return None


def applicant_field_specs(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Turn a schema into a list of form-field specs for the admissions UI."""
    if not schema:
        return []
    return [
        {
            "name": f"score_{subj}",
            "label": subj.replace("_", " ").title(),
            "type": "select",
            "choices": schema.get("choices", []),
            "score_kind": schema.get("score_kind", "letter"),
        }
        for subj in schema.get("subjects", [])
    ]


def schema_choices() -> list[dict[str, str]]:
    """All schemas as a flat list — admin/operator picker."""
    return [{"value": k, "label": v["label"]} for k, v in SCHEMAS.items()]
