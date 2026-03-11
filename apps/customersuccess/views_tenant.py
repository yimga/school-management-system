"""
Section 11.4: Tenant-facing customer success - support co-pilot, guided onboarding.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.setup_studio.services import execute_launch, get_setup_studio_payload

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
            "preview_workspace": {"title": "Live preview workspace", "detail": "", "website_url": "#", "surfaces": []},
            "launch_checklist": [],
            "launch_blockers": [],
            "launch_orchestration": [],
            "launch_ready": False,
            "recommended_blueprint": None,
            "blueprint_rankings": [],
            "recommended_starter_stack": None,
            "data_path_choices": [],
            "ai_recommended": False,
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
        "preview_workspace": studio["preview_workspace"],
        "launch_checklist": studio["launch_checklist"],
        "launch_blockers": studio["launch_blockers"],
        "launch_orchestration": studio["launch_orchestration"],
        "launch_ready": studio["launch_ready"],
        "recommended_blueprint": studio["recommended_blueprint"],
        "blueprint_rankings": studio["blueprint_rankings"],
        "recommended_starter_stack": studio["recommended_starter_stack"],
        "data_path_choices": studio["data_path_choices"],
        "ai_recommended": studio.get("ai_recommended", False),
    })


@login_required
@require_POST
def execute_launch_view(request):
    """Operator-triggered go-live: call execute_launch and redirect back to Setup Studio with message."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context. Go-live is only available in tenant context.")
        return redirect("siteconfig:guided_onboarding")
    result = execute_launch(school.pk, actor_id=request.user.pk)
    if result.get("ok"):
        messages.success(request, "Launch executed. Your school is now approved and launch is recorded.")
    else:
        for err in result.get("errors", []):
            messages.error(request, err)
    return redirect("siteconfig:guided_onboarding")
