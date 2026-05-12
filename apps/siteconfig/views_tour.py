"""
Product tour / walkthrough API (9.5/10 excellence, Workstream 7).
Returns tour steps for a given context so the front-end can drive overlay/spotlight tours.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import TourStep

# Control-plane super-operator tours (BR-13): no TourStep rows required.
DEFAULT_STEPS_SUPER_TRUST = [
    {
        "code": "cp_trust_header",
        "title": "Trust center overview",
        "selector": "[data-tour='cp-trust-header']",
    },
    {
        "code": "cp_trust_cards",
        "title": "Compliance, API, sessions, and audit entry points",
        "selector": "[data-tour='cp-trust-cards']",
    },
    {
        "code": "cp_trust_migration",
        "title": "Migration CSV diff lives under Trust workflows",
        "selector": "[data-tour='cp-trust-migration-link']",
    },
]
DEFAULT_STEPS_SUPER_MIGRATION = [
    {
        "code": "cp_migration_intro",
        "title": "Upload two CSVs to diff keys and spot migration risk",
        "selector": "[data-tour='cp-migration-intro']",
    },
    {
        "code": "cp_migration_form",
        "title": "Baseline vs candidate; optional key column",
        "selector": "[data-tour='cp-migration-form']",
    },
]
DEFAULT_STEPS_SUPER_GOVERNED = [
    {
        "code": "cp_gov_intro",
        "title": "Whitelisted intents only — every run is audited",
        "selector": "[data-tour='cp-gov-intro']",
    },
    {
        "code": "cp_gov_form",
        "title": "Pick intent and run",
        "selector": "[data-tour='cp-gov-form']",
    },
]


def control_plane_default_tour_steps(context: str, user) -> list:
    """Steps for super_operator contexts (testable without DB)."""
    from apps.schools.control_plane import user_has_control_plane_access

    if not getattr(
        user, "is_authenticated", False
    ) or not user_has_control_plane_access(user):
        return []
    if context == "super_trust":
        return list(DEFAULT_STEPS_SUPER_TRUST)
    if context == "super_migration":
        return list(DEFAULT_STEPS_SUPER_MIGRATION)
    if context == "super_governed":
        return list(DEFAULT_STEPS_SUPER_GOVERNED)
    return []


# Default steps when no TourStep records exist (backend_dashboard context).
DEFAULT_STEPS_BACKEND_DASHBOARD = [
    {
        "code": "dashboard_welcome",
        "title": "Your command center",
        "selector": "[data-tour='dashboard-main']",
    },
    {
        "code": "quick_actions",
        "title": "Quick actions",
        "selector": "[data-tour='quick-actions']",
    },
    {
        "code": "school_configuration",
        "title": "School Configuration",
        "selector": "[data-tour='school-configuration-link']",
    },
]


@login_required
@require_GET
def tour_steps_api(request):
    """
    GET ?context=backend_dashboard|super_trust|super_migration|super_governed|...
    Returns { steps: [{ code, title, selector }], context: str }.
    """
    context = (request.GET.get("context") or "backend_dashboard").strip()
    school = getattr(request, "school", None)
    steps = []
    if school:
        qs = TourStep.objects.filter(school=school).order_by("code")[:24]
        for step in qs:
            steps.append(
                {
                    "code": step.code,
                    "title": step.title or step.code,
                    "selector": f"[data-tour='{step.code}']",
                }
            )
    if not steps and context == "backend_dashboard":
        steps = list(DEFAULT_STEPS_BACKEND_DASHBOARD)
    elif not steps:
        steps = control_plane_default_tour_steps(context, request.user)
    return JsonResponse({"steps": steps, "context": context})
