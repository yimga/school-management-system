"""
Section 11.4: Tenant-facing customer success — support co-pilot, guided onboarding.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from .services import get_support_copilot_suggestions, get_guided_onboarding_steps


@login_required
def support_copilot_view(request):
    """Section 11.4: Support co-pilot — suggested actions from interventions, risk alerts, health."""
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
    """Section 11.4: Guided onboarding — checklist of setup steps and progress."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "customersuccess/guided_onboarding.html", {"steps": [], "school": None})
    steps = get_guided_onboarding_steps(school)
    try:
        for s in steps:
            if s.get("link") and s["link"].startswith("/authentication/backend/students/"):
                s["link"] = reverse("accounts:backend_student_list")
            elif s.get("link") and "/backend/" in s["link"]:
                s["link"] = reverse("accounts:backend_dashboard")
    except Exception:
        pass
    return render(request, "customersuccess/guided_onboarding.html", {
        "steps": steps,
        "school": school,
    })
