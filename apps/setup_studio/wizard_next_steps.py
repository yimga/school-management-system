"""Cross-wizard "next steps" smart-suggest registry (v4.00.8 #1).

When a user completes a wizard, the next-best-action is rarely obvious. This
module is the SOT for "what should they do next?" suggestions. The pattern
mirrors apps.platform_runtime.smart_links_kernel but is specifically scoped
to the wizard graph.

A suggestion is keyed by ``(wizard_key, audience)``; the value is a list of
``WizardSuggestion`` ordered by priority. The TenantWizardView's completion
branch renders these as next-step chips on the wizard index.

Pure-Python — no Django imports — so it's SimpleTestCase-friendly and the
unified runner can import this without DB setup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WizardSuggestion:
    """One next-step suggestion after a wizard finishes.

    ``target_wizard_key``: the wizard the user should run next
    ``label_token``: short token (4–10 words) explaining why
    ``priority``: lower number = surfaced first
    ``audience_constraint``: optional — if set, the suggestion only fires
        when the runtime user's audience matches this value. Lets us share
        a single completion handler across audiences while keeping the
        suggestion list audience-precise.
    """

    target_wizard_key: str
    label_token: str
    priority: int = 100
    audience_constraint: str | None = None


# Suggestion registry. Keyed by source wizard_key.
_SUGGESTIONS: dict[str, tuple[WizardSuggestion, ...]] = {
    # Operator graph
    "super_create_school": (
        WizardSuggestion("custom_domain_setup", "wizards.next.add_custom_domain", 10, "operator"),
        WizardSuggestion("cross_platform_whitelabel_branding", "wizards.next.set_branding", 20, "operator"),
        WizardSuggestion("account_migration", "wizards.next.import_existing_data", 30, "operator"),
    ),
    "custom_domain_setup": (
        WizardSuggestion("cross_platform_whitelabel_branding", "wizards.next.match_brand", 10, "operator"),
    ),
    "account_migration": (
        WizardSuggestion("legacy_data_extraction_pipeline", "wizards.next.scale_pipeline", 10, "operator"),
    ),

    # Tenant-admin graph
    "cross_platform_whitelabel_branding": (
        WizardSuggestion("custom_domain_setup", "wizards.next.add_custom_domain", 20, "operator"),
    ),
    "polymorphic_grading_curricula": (
        WizardSuggestion("report_card_template_studio", "wizards.next.build_report_cards", 10, "tenant_admin"),
        WizardSuggestion("exam_schedule_orchestration", "wizards.next.schedule_exams", 20, "tenant_admin"),
    ),
    "report_card_template_studio": (
        WizardSuggestion("institutional_performance_board_reporting", "wizards.next.set_board_reporting", 10, "tenant_admin"),
    ),

    # Teacher graph
    "teacher_self_onboarding": (
        WizardSuggestion("mfa_setup", "wizards.next.enable_mfa", 10, "teacher"),
        WizardSuggestion("teacher_gradebook_setup", "wizards.next.setup_gradebook", 20, "teacher"),
        WizardSuggestion("teacher_attendance_intake", "wizards.next.setup_attendance", 30, "teacher"),
    ),
    "teacher_gradebook_setup": (
        WizardSuggestion("teacher_attendance_intake", "wizards.next.setup_attendance", 10, "teacher"),
    ),
    "teacher_attendance_intake": (
        WizardSuggestion("localized_field_trip_coordinator", "wizards.next.plan_field_trip", 30, "teacher"),
    ),

    # Parent graph
    "parent_link_child": (
        WizardSuggestion("parent_contact_preferences", "wizards.next.set_contact_prefs", 10, "parent"),
        WizardSuggestion("parent_payment_setup", "wizards.next.setup_payments", 20, "parent"),
        WizardSuggestion("mfa_setup", "wizards.next.enable_mfa", 30, "parent"),
    ),
    "parent_onboarding": (
        WizardSuggestion("parent_link_child", "wizards.next.link_a_child", 10, "parent"),
    ),
    "parent_payment_setup": (
        WizardSuggestion("parent_contact_preferences", "wizards.next.set_contact_prefs", 10, "parent"),
    ),

    # Student graph
    "student_self_onboarding": (
        WizardSuggestion("mfa_setup", "wizards.next.enable_mfa", 10, "student"),
        WizardSuggestion("student_course_selection", "wizards.next.choose_courses", 20, "student"),
        WizardSuggestion("personal_graduation_pathway_elective", "wizards.next.plan_graduation", 30, "student"),
    ),
    "student_course_selection": (
        WizardSuggestion("personal_graduation_pathway_elective", "wizards.next.plan_graduation", 10, "student"),
    ),

    # Cross-audience: password rotation generally suggests MFA re-verify
    "student_password_rotation": (
        WizardSuggestion("mfa_setup", "wizards.next.re_verify_mfa", 10, None),
    ),

    # Staff
    "staff_onboarding": (
        WizardSuggestion("mfa_setup", "wizards.next.enable_mfa", 10, "staff"),
    ),
}


def get_suggestions(wizard_key: str, *, audience: str | None = None) -> list[WizardSuggestion]:
    """Return ordered list of next-step suggestions for a completed wizard.

    Filters by ``audience_constraint`` when ``audience`` provided. Returns
    a stable list ordered by priority ASC.
    """
    candidates = _SUGGESTIONS.get(wizard_key, ())
    if audience is not None:
        candidates = tuple(c for c in candidates if c.audience_constraint is None or c.audience_constraint == audience)
    return sorted(candidates, key=lambda c: c.priority)


def list_suggested_targets() -> list[str]:
    """Diagnostic: return the union of every target_wizard_key referenced."""
    return sorted({s.target_wizard_key for ss in _SUGGESTIONS.values() for s in ss})


def source_wizards() -> list[str]:
    """Diagnostic: return wizards that have at least one outgoing suggestion."""
    return sorted(_SUGGESTIONS.keys())
