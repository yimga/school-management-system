"""
Learning delivery (SOT wedges 23–30) and education types (31–43).
Canonical registry: every row has wedge number matching RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §0.2.1.
"""

from __future__ import annotations

# Bump when delivery rows, institution rows, stubs, or terminology change (automation + audits).
CATALOG_VERSION = "2026.03.1"

# Terminology overrides: locale key → { term_key: label } for UI copy (beyond-reach locale packs).
TERMINOLOGY_PACKS: dict[str, dict[str, str]] = {
    "en": {
        "student": "Student",
        "class": "Class",
        "grade": "Grade",
        "report_card": "Report card",
    },
    "fr": {
        "student": "Élève",
        "class": "Classe",
        "grade": "Note",
        "report_card": "Bulletin",
    },
    "en-GB": {
        "student": "Pupil",
        "class": "Form",
        "grade": "Mark",
        "report_card": "School report",
    },
}


def terminology_for_locale(
    locale: str | None, institution_code: str | None = None
) -> dict[str, str]:
    """Merge base locale terms with optional institution-specific aliases."""
    loc = (locale or "en").strip().lower().replace("_", "-")
    base = dict(
        TERMINOLOGY_PACKS.get(loc)
        or TERMINOLOGY_PACKS.get(loc.split("-")[0])
        or TERMINOLOGY_PACKS["en"]
    )
    ic = (institution_code or "").strip().upper()
    if ic == "W43_HIGHER_EDUCATION":
        base.setdefault("student", base.get("student", "Student"))
        base["class"] = "Module"
        base["report_card"] = "Transcript extract"
    elif ic == "W36_ADULT_EDUCATION":
        base["student"] = "Learner"
    return base


# --- 23–30 Learning / delivery (exactly eight; non-negotiable per SOT) ---
LEARNING_DELIVERY_MODES: list[dict[str, str | int]] = [
    {
        "wedge": 23,
        "code": "W23_IN_PERSON",
        "label": "In-person",
        "pack_slugs": "core_scheduling, attendance_classroom, room_resources",
        "notes": "Default classroom delivery; timetables + physical attendance.",
    },
    {
        "wedge": 24,
        "code": "W24_FULLY_ONLINE",
        "label": "Fully online",
        "pack_slugs": "lms_lti_bridge, video_conferencing, portal_comms, evals_continuous",
        "notes": "Remote-first; LTI + synchronous tools + parent portal.",
    },
    {
        "wedge": 25,
        "code": "W25_HYBRID",
        "label": "Hybrid / blended",
        "pack_slugs": "core_scheduling, lms_lti_bridge, portal_comms, video_conferencing",
        "notes": "Split on-site and online; same spine as district LMS motion.",
    },
    {
        "wedge": 26,
        "code": "W26_COMPETENCY_BASED",
        "label": "Competency-based",
        "pack_slugs": "evals_rubrics, evals_continuous, degree_audit_he",
        "notes": "Outcomes / competencies; rubrics + mastery-friendly grading.",
    },
    {
        "wedge": 27,
        "code": "W27_MASTERY_BASED",
        "label": "Mastery-based",
        "pack_slugs": "evals_rubrics, evals_continuous, progression_gates",
        "notes": "Advance on demonstrated mastery; retakes and evidence trails.",
    },
    {
        "wedge": 28,
        "code": "W28_PROJECT_BASED",
        "label": "Project-based",
        "pack_slugs": "evals_rubrics, portfolio_evidence, team_projects",
        "notes": "PBL; portfolios + group assessment hooks.",
    },
    {
        "wedge": 29,
        "code": "W29_SELF_PACED",
        "label": "Self-paced",
        "pack_slugs": "lms_lti_bridge, evals_continuous, async_content",
        "notes": "Async pathways; LTI + continuous assessment.",
    },
    {
        "wedge": 30,
        "code": "W30_COHORT_BASED",
        "label": "Cohort-based",
        "pack_slugs": "core_scheduling, cohort_progress, term_rollover",
        "notes": "Fixed cohort progression; rollover and cohort analytics.",
    },
]

# Legacy delivery codes (pre–wedge-ID) → canonical code for apply_runtime
DELIVERY_CODE_ALIASES: dict[str, str] = {
    "FACE_TO_FACE": "W23_IN_PERSON",
    "HYBRID": "W25_HYBRID",
    "ONLINE_ASYNC": "W29_SELF_PACED",
    "ONLINE_SYNC": "W24_FULLY_ONLINE",
    "COMPETENCY_BASED": "W26_COMPETENCY_BASED",
    "WORKPLACE_APPRENTICESHIP": "W30_COHORT_BASED",
}

# --- 31–43 Education types (exactly thirteen; SOT list) ---
INSTITUTION_TYPE_PACKS: list[dict[str, str | int]] = [
    {
        "wedge": 31,
        "code": "W31_GENERAL_K12",
        "label": "General / academic K–12",
        "pack_slugs": "starter_k12, region_curriculum, core_scheduling",
    },
    {
        "wedge": 32,
        "code": "W32_TVET",
        "label": "Technical / vocational (TVET)",
        "pack_slugs": "tvet_hours, competency_modules, workplace_learning",
    },
    {
        "wedge": 33,
        "code": "W33_TRADE_APPRENTICESHIP",
        "label": "Trade / apprenticeship",
        "pack_slugs": "tvet_hours, employer_portal, dual_transcript",
    },
    {
        "wedge": 34,
        "code": "W34_SPECIALIZED_STEM_ARTS",
        "label": "Specialized (arts, sports, STEM)",
        "pack_slugs": "specialty_tracks, facilities_booking, talent_pathways",
    },
    {
        "wedge": 35,
        "code": "W35_EARLY_YEARS",
        "label": "Early years / pre-K",
        "pack_slugs": "early_years_observations, parent_portal_light, developmental_milestones",
    },
    {
        "wedge": 36,
        "code": "W36_ADULT_EDUCATION",
        "label": "Adult education",
        "pack_slugs": "session_based_enrollment, flexible_billing, evening_scheduling",
    },
    {
        "wedge": 37,
        "code": "W37_PROFESSIONAL_CORPORATE",
        "label": "Professional development / corporate",
        "pack_slugs": "credential_tracking, cohort_training, compliance_credits",
    },
    {
        "wedge": 38,
        "code": "W38_LANGUAGE_SCHOOL",
        "label": "Language schools",
        "pack_slugs": "level_placement, session_cycles, multi_language_reports",
    },
    {
        "wedge": 39,
        "code": "W39_EXAM_PREP_TUTORING",
        "label": "Exam prep / tutoring",
        "pack_slugs": "session_packages, outcome_tracking, small_group_scheduling",
    },
    {
        "wedge": 40,
        "code": "W40_SPECIAL_EDUCATION",
        "label": "Special education",
        "pack_slugs": "iep_tracking, accommodations, multi_discipline_team",
    },
    {
        "wedge": 41,
        "code": "W41_GIFTED_ADVANCED",
        "label": "Gifted / advanced",
        "pack_slugs": "acceleration_paths, enrichment_catalog, differentiation",
    },
    {
        "wedge": 42,
        "code": "W42_ALTERNATIVE_PROVISION",
        "label": "Alternative provision",
        "pack_slugs": "flexible_attendance, outreach_logging, safeguarding_escalation",
    },
    {
        "wedge": 43,
        "code": "W43_HIGHER_EDUCATION",
        "label": "Higher education",
        "pack_slugs": "degree_audit, semester_catalog, graduate_research",
    },
]

INSTITUTION_CODE_ALIASES: dict[str, str] = {
    "GENERAL_K12": "W31_GENERAL_K12",
    "EARLY_YEARS": "W35_EARLY_YEARS",
    "TVET_TRADE": "W32_TVET",
    "INTERNATIONAL_SCHOOL": "W31_GENERAL_K12",
    "FAITH_BASED": "W31_GENERAL_K12",
    "HIGHER_ED": "W43_HIGHER_EDUCATION",
    "ADULT_EDUCATION": "W36_ADULT_EDUCATION",
    "LANGUAGE_SCHOOL": "W38_LANGUAGE_SCHOOL",
}

MINISTRY_REPORT_STUBS: dict[str, list[dict[str, str]]] = {
    "W31_GENERAL_K12": [
        {"slug": "stub_census_headcount", "label": "Census / headcount (stub)"},
        {"slug": "stub_attendance_summary", "label": "Attendance summary (stub)"},
    ],
    "W32_TVET": [
        {"slug": "stub_tvet_contact_hours", "label": "TVET contact hours (stub)"},
        {"slug": "stub_competency_matrix", "label": "Competency matrix export (stub)"},
    ],
    "W33_TRADE_APPRENTICESHIP": [
        {
            "slug": "stub_apprenticeship_log",
            "label": "Apprenticeship placement log (stub)",
        },
        {"slug": "stub_employer_signoff", "label": "Employer sign-off register (stub)"},
    ],
    "W34_SPECIALIZED_STEM_ARTS": [
        {"slug": "stub_talent_pathway", "label": "Talent pathway summary (stub)"},
    ],
    "W35_EARLY_YEARS": [
        {"slug": "stub_eyfs_development", "label": "EYFS / development summary (stub)"},
    ],
    "W36_ADULT_EDUCATION": [
        {"slug": "stub_adult_completion", "label": "Adult learner completion (stub)"},
    ],
    "W37_PROFESSIONAL_CORPORATE": [
        {"slug": "stub_pd_credit_hours", "label": "PD credit hours (stub)"},
    ],
    "W38_LANGUAGE_SCHOOL": [
        {"slug": "stub_cefr_progression", "label": "CEFR progression (stub)"},
    ],
    "W39_EXAM_PREP_TUTORING": [
        {"slug": "stub_exam_readiness", "label": "Exam readiness cohort (stub)"},
    ],
    "W40_SPECIAL_EDUCATION": [
        {"slug": "stub_iep_summary", "label": "IEP service summary (stub)"},
    ],
    "W41_GIFTED_ADVANCED": [
        {"slug": "stub_acceleration_register", "label": "Acceleration register (stub)"},
    ],
    "W42_ALTERNATIVE_PROVISION": [
        {
            "slug": "stub_alternative_attendance",
            "label": "Alternative provision attendance (stub)",
        },
    ],
    "W43_HIGHER_EDUCATION": [
        {"slug": "stub_transcript_export", "label": "Official transcript shell (stub)"},
        {"slug": "stub_registrar_census", "label": "Registrar census (stub)"},
    ],
    "DEFAULT": [
        {"slug": "stub_enrollment_register", "label": "Enrollment register (stub)"}
    ],
}

# ISO 3166-1 alpha-2 → statutory / privacy narrative for ministry stub PDFs (shell; §11.4 depth = live connectors).
STATUTORY_JURISDICTION_HINTS: dict[str, dict[str, str]] = {
    "US": {
        "label": "United States",
        "framework": "FERPA; state reporting varies by SEA — replace shell with live extracts.",
    },
    "GB": {
        "label": "United Kingdom",
        "framework": "DfE / UK statutory returns — align with GBR region pack and report library.",
    },
    "NG": {
        "label": "Nigeria",
        "framework": "WAEC / state ministry — use WAEC region pack + statutory roadmap.",
    },
    "GH": {
        "label": "Ghana",
        "framework": "WASSCE / GES — West Africa pack defaults.",
    },
    "KE": {
        "label": "Kenya",
        "framework": "CBC / ministry reporting — Kenya CBC blueprint alignment.",
    },
    "CM": {
        "label": "Cameroon",
        "framework": "Francophone / Anglophone MoE — dual policy packs.",
    },
    "AE": {
        "label": "United Arab Emirates",
        "framework": "MoE / KHDA-style governance — UAE MoE+IB blueprint.",
    },
    "AU": {
        "label": "Australia",
        "framework": "ACARA / state registers — ACARA blueprint + AUS pack.",
    },
    "NZ": {
        "label": "New Zealand",
        "framework": "MoE NZ — NZL pack + statutory exports.",
    },
    "CA": {
        "label": "Canada",
        "framework": "Provincial ministries — PIPEDA + provincial reporting.",
    },
    "FR": {
        "label": "France",
        "framework": "Ministère — EU GDPR + national bulletin norms.",
    },
    "DE": {
        "label": "Germany",
        "framework": "KMK / Länder — EU GDPR + state education law.",
    },
    "BR": {
        "label": "Brazil",
        "framework": "MEC / INEP — BRA pack + national census narratives.",
    },
    "IN": {
        "label": "India",
        "framework": "CBSE / state boards — India CBSE blueprint.",
    },
    "SG": {
        "label": "Singapore",
        "framework": "MOE Singapore — Asia pack + ministry stubs.",
    },
    "CO": {
        "label": "Colombia",
        "framework": "MEN — LATAM_ES pack.",
    },
}

# Suggested ISO alpha-2 for manager-host ministry PDF preview (stub shell; not legal filing).
INSTITUTION_TYPE_STATUTORY_COUNTRY_HINT: dict[str, str] = {
    "W31_GENERAL_K12": "US",
    "W32_TVET": "GB",
    "W33_TRADE_APPRENTICESHIP": "GB",
    "W34_SPECIALIZED_STEM_ARTS": "US",
    "W35_EARLY_YEARS": "GB",
    "W36_ADULT_EDUCATION": "US",
    "W37_PROFESSIONAL_CORPORATE": "US",
    "W38_LANGUAGE_SCHOOL": "GB",
    "W39_EXAM_PREP_TUTORING": "US",
    "W40_SPECIAL_EDUCATION": "US",
    "W41_GIFTED_ADVANCED": "US",
    "W42_ALTERNATIVE_PROVISION": "GB",
    "W43_HIGHER_EDUCATION": "US",
}


def normalize_delivery_code(code: str) -> str:
    c = str(code or "").strip().upper()
    return DELIVERY_CODE_ALIASES.get(c, c)


def normalize_institution_code(code: str) -> str:
    c = str(code or "").strip().upper()
    return INSTITUTION_CODE_ALIASES.get(c, c)


def delivery_wedges() -> list[int]:
    return [int(x["wedge"]) for x in LEARNING_DELIVERY_MODES]


def institution_wedges() -> list[int]:
    return [int(x["wedge"]) for x in INSTITUTION_TYPE_PACKS]
