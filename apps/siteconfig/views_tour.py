"""
Product tour / walkthrough API (9.5/10 excellence, Workstream 7).
Returns tour steps for a given context so the front-end can drive overlay/spotlight tours.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import TourStep


# Default steps when no TourStep records exist (backend_dashboard context).
DEFAULT_STEPS_BACKEND_DASHBOARD = [
    {"code": "dashboard_welcome", "title": "Your command center", "selector": "[data-tour='dashboard-main']"},
    {"code": "quick_actions", "title": "Quick actions", "selector": "[data-tour='quick-actions']"},
    {"code": "setup_studio", "title": "Setup Studio", "selector": "[data-tour='setup-studio-link']"},
]


@login_required
@require_GET
def tour_steps_api(request):
    """
    GET ?context=backend_dashboard|setup_studio|marketplace
    Returns { steps: [{ code, title, selector }], context: str }.
    """
    context = (request.GET.get("context") or "backend_dashboard").strip()
    school = getattr(request, "school", None)
    steps = []
    if school:
        qs = TourStep.objects.filter(school=school).order_by("code")[:24]
        for step in qs:
            steps.append({
                "code": step.code,
                "title": step.title or step.code,
                "selector": f"[data-tour='{step.code}']",
            })
    if not steps and context == "backend_dashboard":
        steps = list(DEFAULT_STEPS_BACKEND_DASHBOARD)
    return JsonResponse({"steps": steps, "context": context})
