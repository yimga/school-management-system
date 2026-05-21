"""
Operator direction model for tenant onboarding (code SOT).

Mirrors generated ``docs/generated/tenant_onboarding_operator_direction_model.json``.
Each step defines owner, blocker logic, and AI guidance behavior without secrets.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

OPERATOR_ROLES = (
    "platform_implementation_operator",
    "school_owner",
    "tenant_admin",
    "registrar",
    "bursar",
    "academic_lead",
    "teacher_lead",
    "support_success_operator",
)

LAUNCH_LANES: tuple[dict[str, Any], ...] = (
    {
        "key": "start_setup",
        "label": _("Start setup"),
        "purpose": _("Open the activation checklist and first incomplete step."),
        "url_name": "siteconfig:onboarding",
        "owner": "tenant_admin",
        "required": True,
    },
    {
        "key": "essentials",
        "label": _("Complete essentials"),
        "purpose": _("Academic year, people, classes, and guided configuration."),
        "url_name": "siteconfig:onboarding",
        "owner": "tenant_admin",
        "required": True,
    },
    {
        "key": "import_data",
        "label": _("Import data"),
        "purpose": _("Migration Cloud connectors, CSV import, and quarantine review."),
        "url_name": "school_setup_imports",
        "owner": "registrar",
        "required": False,
    },
    {
        "key": "operations",
        "label": _("Configure operations"),
        "purpose": _("Billing, workflows, offline sync, and security surfaces."),
        "url_name": "school_money",
        "owner": "bursar",
        "required": False,
    },
    {
        "key": "readiness",
        "label": _("Review readiness"),
        "purpose": _("Health score, blockers, and launch checklist."),
        "url_name": "school_studio",
        "owner": "school_owner",
        "required": True,
    },
    {
        "key": "launch",
        "label": _("Launch school"),
        "purpose": _("Execute guided launch when checklist and health allow."),
        "url_name": "siteconfig:guided_onboarding",
        "owner": "school_owner",
        "required": True,
    },
)

ONBOARDING_DIRECTION_STEPS: tuple[dict[str, Any], ...] = (
    {
        "step_key": "academic_year",
        "name": _("Academic year"),
        "owner": "academic_lead",
        "required": True,
        "prerequisites": [],
        "blocker_if": "no_active_academic_year",
        "completion": "data_driven_or_operator_mark",
        "next_action_hint": _("Add at least one academic year before importing classes."),
        "help_url_name": "siteconfig:onboarding_step",
        "ai_guidance": "route_aware_setup_step",
        "proof": "apps.platform_runtime.onboarding",
    },
    {
        "step_key": "students",
        "name": _("Students"),
        "owner": "registrar",
        "required": True,
        "prerequisites": ["academic_year"],
        "blocker_if": "zero_active_students",
        "completion": "data_driven",
        "next_action_hint": _("Import or enroll students from the student roster."),
        "help_url_name": "accounts:backend_student_list",
        "ai_guidance": "route_aware_setup_step",
        "proof": "apps.platform_runtime.onboarding",
    },
    {
        "step_key": "teachers",
        "name": _("Teachers / staff"),
        "owner": "tenant_admin",
        "required": True,
        "prerequisites": [],
        "blocker_if": "zero_teachers",
        "completion": "data_driven",
        "next_action_hint": _("Invite teaching staff before assigning classes."),
        "help_url_name": "accounts:backend_teacher_list",
        "ai_guidance": "route_aware_setup_step",
        "proof": "apps.platform_runtime.onboarding",
    },
    {
        "step_key": "guided_configuration",
        "name": _("Tenant settings"),
        "owner": "tenant_admin",
        "required": True,
        "prerequisites": ["academic_year"],
        "blocker_if": "site_settings_incomplete",
        "completion": "data_driven",
        "next_action_hint": _("Finish branding and runtime settings in Configure."),
        "help_url_name": "siteconfig:console_domains_hub",
        "ai_guidance": "missing_context_fallback",
        "proof": "apps.platform_runtime.onboarding",
    },
    {
        "step_key": "plan_entitlements",
        "name": _("Plan review"),
        "owner": "bursar",
        "required": False,
        "prerequisites": [],
        "blocker_if": "no_plan_assigned",
        "completion": "data_driven",
        "next_action_hint": _("Review plan and billing readiness."),
        "help_url_name": "siteconfig:billing_plan_readonly",
        "ai_guidance": "billing_usage_explain",
        "proof": "apps.platform_runtime.onboarding",
    },
)


def launch_lanes_for_template() -> list[dict[str, Any]]:
    """Resolve URL names to paths for templates (tenant urlconf)."""
    from django.urls import NoReverseMatch, reverse

    rows: list[dict[str, Any]] = []
    for lane in LAUNCH_LANES:
        row = dict(lane)
        url_name = str(row.get("url_name") or "")
        try:
            row["url"] = reverse(url_name, urlconf="config.tenant_urls")
        except NoReverseMatch:
            try:
                row["url"] = reverse(url_name)
            except NoReverseMatch:
                row["url"] = ""
        rows.append(row)
    return rows


def direction_steps_export() -> list[dict[str, Any]]:
    """JSON-serializable operator direction rows."""
    out: list[dict[str, Any]] = []
    for step in ONBOARDING_DIRECTION_STEPS:
        out.append(
            {
                "step_key": step["step_key"],
                "name": str(step["name"]),
                "owner": step["owner"],
                "required": step["required"],
                "prerequisites": list(step["prerequisites"]),
                "blocker_if": step["blocker_if"],
                "completion": step["completion"],
                "next_action_hint": str(step["next_action_hint"]),
                "help_url_name": step.get("help_url_name"),
                "ai_guidance": step["ai_guidance"],
                "proof": step["proof"],
            }
        )
    return out
