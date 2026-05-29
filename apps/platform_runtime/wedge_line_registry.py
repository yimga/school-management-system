"""
Line-by-line registry for SOT wedges 1–45 (single machine-readable source).

Used by:
- scripts/verify_wedge_line_registry.py (URL reverse + seed slug checks + canonical ``super:wedge_operator_detail`` for ids 1..45)
- apps/schools/super_views_wedge.py (beachhead blueprint hints, ``/super/wedge/<id>/`` operator pages)

**Continuous depth** (statutory PDFs, ERP patterns, dashboards-as-decision-engines) stays in
§0.2.1.3 / §11.4 — this module maps each wedge to **shipped surfaces** and **verification phase**.
"""

from __future__ import annotations

from typing import Final

# Phase 3 beachhead: marketplace blueprint slugs (seed_blueprint_policy_packs.py) — W1 / W3 depth
BEACHHEAD_BLUEPRINT_PACKS: Final[tuple[dict[str, str], ...]] = (
    {"slug": "ib-world-school", "label": "IB World School"},
    {"slug": "uk-gcse-alevel", "label": "UK GCSE / A-Level"},
    {"slug": "us-k12-district", "label": "US K-12 District"},
    {"slug": "uae-moe-ib", "label": "UAE MoE + IB"},
)


def wedge_phase(wedge_id: int) -> int:
    """Execution phase (10 wedges per band) matching validate_wedges_phase.py."""
    if wedge_id <= 10:
        return 1
    if wedge_id <= 20:
        return 2
    if wedge_id <= 30:
        return 3
    if wedge_id <= 40:
        return 4
    return 5


def _urls(*names: str) -> tuple[str, ...]:
    return names


# Manager URL names (config.manager_urls) — empty tuple = catalog/file-only wedge
WEDGE_LINES: Final[tuple[dict[str, int | str | tuple[str, ...]], ...]] = (
    # Tier A — beachheads 1–6
    {
        "id": 1,
        "name": "International K–12 SIS",
        "tier": "A",
        "phase": 1,
        "urls": _urls(
            "super:curriculum_packs",
            "studio_os:launch",
            "super:one_sis_any_lms",
            "super:migration_cloud",
        ),
    },
    {
        "id": 2,
        "name": "LMS integration",
        "tier": "A",
        "phase": 1,
        "urls": _urls("super:one_sis_any_lms", "apicenter:dashboard"),
    },
    {
        "id": 3,
        "name": "UK / British-curriculum",
        "tier": "A",
        "phase": 1,
        "urls": _urls("super:curriculum_packs", "super:geography", "super:trust_center"),
    },
    {
        "id": 4,
        "name": "District / enterprise",
        "tier": "A",
        "phase": 1,
        "urls": _urls(
            "super:district_enterprise",
            "super:trust_center",
            "super:migration_cloud",
            "super:geography",
        ),
    },
    {
        "id": 5,
        "name": "Advancement",
        "tier": "A",
        "phase": 1,
        "urls": _urls(
            "super:advancement_hub",
            "super:advancement_phase2_placeholder",
        ),
    },
    {
        "id": 6,
        "name": "Higher-ed",
        "tier": "A",
        "phase": 1,
        "urls": _urls("super:he_pack", "super:learning_delivery_packs"),
    },
    # Tier B — geography 7–13
    {
        "id": 7,
        "name": "Africa (region packs)",
        "tier": "B",
        "phase": 1,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    {
        "id": 8,
        "name": "Asia",
        "tier": "B",
        "phase": 1,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    {
        "id": 9,
        "name": "Europe (beyond UK)",
        "tier": "B",
        "phase": 1,
        "urls": _urls("super:geography", "super:trust_center"),
    },
    {
        "id": 10,
        "name": "North America",
        "tier": "B",
        "phase": 1,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    {
        "id": 11,
        "name": "South America",
        "tier": "B",
        "phase": 2,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    {
        "id": 12,
        "name": "Oceania",
        "tier": "B",
        "phase": 2,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    {
        "id": 13,
        "name": "MENA",
        "tier": "B",
        "phase": 2,
        "urls": _urls("super:geography", "super:curriculum_packs"),
    },
    # Tier C — education systems 14–22
    {
        "id": 14,
        "name": "Public / state",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:create_school_wizard"),
    },
    {
        "id": 15,
        "name": "Private / independent",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:create_school_wizard"),
    },
    {
        "id": 16,
        "name": "Charter",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:blueprints_catalog"),
    },
    {
        "id": 17,
        "name": "International",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:curriculum_packs"),
    },
    {
        "id": 18,
        "name": "Faith-based",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:blueprints_catalog"),
    },
    {
        "id": 19,
        "name": "Home-school / hybrid",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:create_school_wizard"),
    },
    {
        "id": 20,
        "name": "Government / ministry",
        "tier": "C",
        "phase": 2,
        "urls": _urls("super:education_systems", "super:ministry_report_stubs"),
    },
    {
        "id": 21,
        "name": "NGO",
        "tier": "C",
        "phase": 3,
        "urls": _urls("super:education_systems", "super:create_school_wizard"),
    },
    {
        "id": 22,
        "name": "Multi-campus / group",
        "tier": "C",
        "phase": 3,
        "urls": _urls(
            "super:education_systems",
            "super:group_campuses",
            "super:mat_group_hub_dashboard",
            "super:mat_group_hub_create",
        ),
    },
    # Tier D — delivery 23–30
    {
        "id": 23,
        "name": "In-person",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs"),
    },
    {
        "id": 24,
        "name": "Fully online",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs", "super:one_sis_any_lms"),
    },
    {
        "id": 25,
        "name": "Hybrid / blended",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs", "super:one_sis_any_lms"),
    },
    {
        "id": 26,
        "name": "Competency-based",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs"),
    },
    {
        "id": 27,
        "name": "Mastery-based",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs"),
    },
    {
        "id": 28,
        "name": "Project-based",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs"),
    },
    {
        "id": 29,
        "name": "Self-paced",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs", "super:one_sis_any_lms"),
    },
    {
        "id": 30,
        "name": "Cohort-based",
        "tier": "D",
        "phase": 3,
        "urls": _urls("super:learning_delivery_packs"),
    },
    # Tier E — types 31–43
    {
        "id": 31,
        "name": "General / academic K–12",
        "tier": "E",
        "phase": 4,
        "urls": _urls(
            "super:learning_delivery_packs",
            "super:ministry_report_stubs",
            "super:learning_institution_catalog_json",
        ),
    },
    {
        "id": 32,
        "name": "TVET",
        "tier": "E",
        "phase": 4,
        "urls": _urls(
            "super:learning_delivery_packs",
            "super:ministry_report_stubs",
        ),
    },
    {
        "id": 33,
        "name": "Trade / apprenticeship",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 34,
        "name": "Specialized (arts, STEM, sports)",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 35,
        "name": "Early years / pre-K",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 36,
        "name": "Adult education",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 37,
        "name": "Professional development / corporate",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 38,
        "name": "Language schools",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 39,
        "name": "Exam prep / tutoring",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 40,
        "name": "Special education",
        "tier": "E",
        "phase": 4,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 41,
        "name": "Gifted / advanced",
        "tier": "E",
        "phase": 5,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 42,
        "name": "Alternative provision",
        "tier": "E",
        "phase": 5,
        "urls": _urls("super:learning_delivery_packs", "super:ministry_report_stubs"),
    },
    {
        "id": 43,
        "name": "Higher education (type)",
        "tier": "E",
        "phase": 5,
        "urls": _urls("super:learning_delivery_packs", "super:he_pack", "super:ministry_report_stubs"),
    },
    # Tier F — glue 44–45
    {
        "id": 44,
        "name": "Clever/ClassLink-style roster + SSO",
        "tier": "F",
        "phase": 5,
        "urls": _urls(
            "super:one_sis_any_lms",
            "super:native_roster_connectors",
            "apicenter:dashboard",
            "super:runtime_truth_hub",
        ),
    },
    {
        "id": 45,
        "name": "Identity and access federation",
        "tier": "F",
        "phase": 5,
        "urls": _urls(
            "super:trust_center",
            "super:one_sis_any_lms",
            "super:runtime_truth_hub",
        ),
    },
)


def assert_wedge_lines_complete() -> None:
    if len(WEDGE_LINES) != 45:
        raise ValueError(f"WEDGE_LINES must have 45 rows, got {len(WEDGE_LINES)}")
    for i, row in enumerate(WEDGE_LINES, start=1):
        wid = row["id"]
        if wid != i:
            raise ValueError(f"WEDGE_LINES order: expected id {i}, got {wid}")
        ph = row["phase"]
        if ph != wedge_phase(int(wid)):
            raise ValueError(f"Wedge {wid}: phase {ph} != wedge_phase({wid})={wedge_phase(int(wid))}")
