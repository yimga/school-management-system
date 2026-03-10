"""
Section 11.4: Tenant-facing customer success - support co-pilot, guided onboarding.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.setup_studio.services import get_setup_studio_payload

from .services import get_support_copilot_suggestions


@login_required
def support_copilot_view(request):
    """Section 11.4: Support co-pilot - suggested actions from interventions, risk alerts, health."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "customersuccess/support_copilot.html", {"suggestions": [], "school": None})
    suggestions = get_support_copilot_suggestions(school)
    return render(request, "customersuccess/support_copilot.html", {
        "suggestions": suggestions,
        "school": school,
    })


@login_required
def guided_onboarding_view(request):
    """Section 11.4: Guided onboarding - Setup Studio backed by persisted setup state."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "customersuccess/guided_onboarding.html", {
            "steps": [],
            "school": None,
            "current_step": None,
            "progress_percent": 0,
            "setup_health_score": 0,
            "health_summary": {"label": "Needs attention", "detail": "No school context was detected for Setup Studio.", "tone": "risk"},
            "recommended_next": None,
            "recommendations": [],
            "role_previews": [],
            "preview_cards": [],
            "launch_checklist": [],
            "launch_blockers": [],
            "launch_ready": False,
            "recommended_blueprint": None,
            "recommended_starter_stack": None,
        })

    studio = get_setup_studio_payload(school)
    return render(request, "customersuccess/guided_onboarding.html", {
        "steps": studio["steps"],
        "school": school,
        "current_step": studio["current_step"],
        "progress_percent": studio["progress_percent"],
        "setup_health_score": studio["health_score"],
        "health_summary": studio["health_summary"],
        "recommended_next": studio["recommended_next"],
        "recommendations": studio["recommendations"],
        "role_previews": studio["role_previews"],
        "preview_cards": studio["preview_cards"],
        "launch_checklist": studio["launch_checklist"],
        "launch_blockers": studio["launch_blockers"],
        "launch_ready": studio["launch_ready"],
        "recommended_blueprint": studio["recommended_blueprint"],
        "recommended_starter_stack": studio["recommended_starter_stack"],
    })
