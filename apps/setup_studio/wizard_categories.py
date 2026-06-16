"""Lifecycle-stage taxonomy for grouping setup wizards on the index surface.

The JSON-driven wizard registry carries no ``category`` field — every wizard's
``category`` is ``None`` — so the tenant Setup-Wizards index would render a single
flat A→Z grid of cards with no grouping (the "cramped flat list" defect).

This module is the SINGLE platform-constant mapping ``wizard_key`` → a **lifecycle
stage**. It is config, not bespoke UI copy: the engine, index, and gate still read
``audience`` as the SOT; this only decides which labeled stage a card lands in on
the index page. A wizard with no entry falls into the default stage, so the map is
additive and never hides a wizard.

The four stages model a school's onboarding journey top-down — exactly the
"setup guide" shape Shopify/Salesforce use:

1. **Get started** — stand the school up (identity, access, people, data).
2. **Configure** — set up how it runs (academics, finance, communications).
3. **Operate** — run it day to day (engagement, reporting, maintenance).
4. **Govern** — keep it safe and compliant (safeguarding, governance, controls).

Section ORDER is ``CATEGORY_ORDER`` so the index reads as a numbered progression.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# Stable display order of the lifecycle stages on the index (numbered 1..4).
CATEGORY_ORDER: tuple[str, ...] = (
    "get_started",
    "configure",
    "operate",
    "govern",
)

# Human-readable stage labels (gettext-wrapped so they translate).
CATEGORY_LABELS: dict[str, object] = {
    "get_started": _("Get started"),
    "configure": _("Configure"),
    "operate": _("Operate"),
    "govern": _("Govern"),
}

# One-line stage taglines shown under each section heading on the bespoke index.
CATEGORY_DESCRIPTIONS: dict[str, object] = {
    "get_started": _("Stand your school up — identity, secure access, and your people."),
    "configure": _("Set up how your school runs — academics, finance, and communications."),
    "operate": _("Keep things running — engagement, reporting, and ongoing maintenance."),
    "govern": _("Stay safe and compliant — safeguarding, governance, and platform controls."),
}

# Fallback stage for any wizard not explicitly mapped below. "configure" is the
# safest default — most unmapped flows are run-of-the-house configuration.
DEFAULT_CATEGORY = "configure"

# wizard_key → lifecycle stage. Only keys present here are placed; everything
# else falls into DEFAULT_CATEGORY. Derived from each wizard's role in the
# onboarding journey, not its audience (audience stays the authorization SOT).
WIZARD_CATEGORY_BY_KEY: dict[str, str] = {
    # 1 — Get started: stand the school up.
    "mfa_setup": "get_started",
    "custom_domain_setup": "get_started",
    "super_create_school": "get_started",
    "account_migration": "get_started",
    "legacy_data_extraction_pipeline": "get_started",
    "staff_onboarding": "get_started",
    "teacher_self_onboarding": "get_started",
    "student_self_onboarding": "get_started",
    "parent_onboarding": "get_started",
    "parent_link_child": "get_started",
    # 2 — Configure: set up how the school runs.
    "cross_platform_whitelabel_branding": "configure",
    "teacher_gradebook_setup": "configure",
    "teacher_attendance_intake": "configure",
    "exam_schedule_orchestration": "configure",
    "report_card_template_studio": "configure",
    "polymorphic_grading_curricula": "configure",
    "personal_graduation_pathway_elective": "configure",
    "student_course_selection": "configure",
    "library_inventory_management": "configure",
    "dynamic_multi_campus_scheduling": "configure",
    "cashless_campus_pos": "configure",
    "local_first_fintech_tax_matrix": "configure",
    "parent_payment_setup": "configure",
    "omnichannel_communication_routing": "configure",
    "ai_helpcenter_knowledge_injection": "configure",
    # 3 — Operate: run it day to day.
    "localized_activity_asset_marketplace": "operate",
    "alumni_engagement_pipeline": "operate",
    "parent_contact_preferences": "operate",
    "human_capital_shift_substitute_market": "operate",
    "institutional_performance_board_reporting": "operate",
    "student_password_rotation": "operate",
    "localized_field_trip_coordinator": "operate",
    # 4 — Govern: keep it safe and compliant.
    "dynamic_safeguarding_incident_medical": "govern",
    "jit_operator_compliance_safeguarding": "govern",
    "multi_campus_local_sovereignty": "govern",
    "self_healing_observability_guard": "govern",
}


def category_for(wizard_key: str) -> str:
    """Return the lifecycle-stage key for a wizard, defaulting to DEFAULT_CATEGORY."""
    return WIZARD_CATEGORY_BY_KEY.get(wizard_key, DEFAULT_CATEGORY)


def group_wizards_by_category(wizards):
    """Group an iterable of WizardDefinition into ordered stage sections.

    Returns a list of ``{"key", "label", "description", "step", "wizards"}`` dicts
    in ``CATEGORY_ORDER``, omitting empty stages. ``step`` is the 1-based stage
    number for the numbered-progression UI. Wizards keep their incoming order
    within a stage (callers pass them already sorted by wizard_key).
    """
    buckets: dict[str, list] = {key: [] for key in CATEGORY_ORDER}
    for wiz in wizards:
        bucket = category_for(getattr(wiz, "wizard_key", ""))
        if bucket not in buckets:
            bucket = DEFAULT_CATEGORY
        buckets[bucket].append(wiz)
    groups = []
    step = 0
    for key in CATEGORY_ORDER:
        items = buckets.get(key) or []
        if not items:
            continue
        step += 1
        groups.append({
            "key": key,
            "label": CATEGORY_LABELS.get(key, key),
            "description": CATEGORY_DESCRIPTIONS.get(key, ""),
            "step": step,
            "wizards": items,
        })
    return groups
