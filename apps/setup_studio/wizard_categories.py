"""Category taxonomy for grouping setup wizards on the index surface.

The JSON-driven wizard registry carries no ``category`` field — every wizard's
``category`` is ``None`` — so the tenant Setup-Wizards index rendered a single
flat A→Z grid of ~20 cards with no grouping (the "cramped flat list" defect).

This module is the SINGLE platform-constant mapping ``wizard_key`` → a section
label. It is config, not bespoke UI copy: the engine, index, and gate still read
``audience`` as the SOT; this only decides which labeled section a card lands in
on the index page. A wizard with no entry falls into the default bucket, so the
map is additive and never hides a wizard.

Section ORDER is the order keys first appear in ``CATEGORY_ORDER`` so the index
reads top-down from "get-started" toward advanced/platform flows.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# Stable display order of the sections on the index.
CATEGORY_ORDER: tuple[str, ...] = (
    "essentials",
    "academics",
    "finance",
    "communications",
    "people",
    "compliance",
    "platform",
    "more",
)

# Human-readable section labels (gettext-wrapped so they translate).
CATEGORY_LABELS: dict[str, object] = {
    "essentials": _("Get started"),
    "academics": _("Academics"),
    "finance": _("Finance & payments"),
    "communications": _("Communications"),
    "people": _("People & onboarding"),
    "compliance": _("Safety & compliance"),
    "platform": _("Platform & operations"),
    "more": _("More setup"),
}

# Fallback section for any wizard not explicitly mapped below.
DEFAULT_CATEGORY = "more"

# wizard_key → category. Only keys present here are placed; everything else
# falls into DEFAULT_CATEGORY. Derived from each wizard's domain, not its
# audience (audience stays the authorization SOT).
WIZARD_CATEGORY_BY_KEY: dict[str, str] = {
    # Get started
    "mfa_setup": "essentials",
    "custom_domain_setup": "essentials",
    "cross_platform_whitelabel_branding": "essentials",
    # Academics
    "teacher_gradebook_setup": "academics",
    "teacher_attendance_intake": "academics",
    "exam_schedule_orchestration": "academics",
    "report_card_template_studio": "academics",
    "polymorphic_grading_curricula": "academics",
    "personal_graduation_pathway_elective": "academics",
    "student_course_selection": "academics",
    "library_inventory_management": "academics",
    "dynamic_multi_campus_scheduling": "academics",
    # Finance & payments
    "cashless_campus_pos": "finance",
    "local_first_fintech_tax_matrix": "finance",
    "parent_payment_setup": "finance",
    "localized_activity_asset_marketplace": "finance",
    # Communications
    "omnichannel_communication_routing": "communications",
    "ai_helpcenter_knowledge_injection": "communications",
    "alumni_engagement_pipeline": "communications",
    "parent_contact_preferences": "communications",
    # People & onboarding
    "staff_onboarding": "people",
    "parent_onboarding": "people",
    "parent_link_child": "people",
    "student_self_onboarding": "people",
    "teacher_self_onboarding": "people",
    "student_password_rotation": "people",
    "human_capital_shift_substitute_market": "people",
    # Safety & compliance
    "dynamic_safeguarding_incident_medical": "compliance",
    "jit_operator_compliance_safeguarding": "compliance",
    # Platform & operations
    "account_migration": "platform",
    "legacy_data_extraction_pipeline": "platform",
    "institutional_performance_board_reporting": "platform",
    "multi_campus_local_sovereignty": "platform",
    "self_healing_observability_guard": "platform",
    "super_create_school": "platform",
}


def category_for(wizard_key: str) -> str:
    """Return the section key for a wizard, defaulting to DEFAULT_CATEGORY."""
    return WIZARD_CATEGORY_BY_KEY.get(wizard_key, DEFAULT_CATEGORY)


def group_wizards_by_category(wizards):
    """Group an iterable of WizardDefinition into ordered (label, key, wizards) tuples.

    Returns a list of ``{"key", "label", "wizards"}`` dicts in ``CATEGORY_ORDER``,
    omitting empty sections. Wizards keep their incoming order within a section
    (callers pass them already sorted by wizard_key).
    """
    buckets: dict[str, list] = {key: [] for key in CATEGORY_ORDER}
    for wiz in wizards:
        bucket = category_for(getattr(wiz, "wizard_key", ""))
        if bucket not in buckets:
            bucket = DEFAULT_CATEGORY
        buckets[bucket].append(wiz)
    groups = []
    for key in CATEGORY_ORDER:
        items = buckets.get(key) or []
        if not items:
            continue
        groups.append({
            "key": key,
            "label": CATEGORY_LABELS.get(key, key),
            "wizards": items,
        })
    return groups
