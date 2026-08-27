"""Move 4 — tenant-visible health dashboard."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.customersuccess.models import (
    TenantHealthScore,
    TenantInterventionSuggestion,
    TenantRiskAlert,
)


@login_required
@require_GET
def tenant_health_dashboard(request):
    """Render a small dashboard showing the tenant's most-recent TenantHealthScore
    plus open risk alerts and intervention suggestions.

    School-admin only. The page renders TenantRiskAlert.reason and
    .suggested_action verbatim -- internal customer-success commentary about the
    school's own operational failure, written for operators ("Tenant inactive --
    Reach out to re-engage the school and confirm staff have working logins").
    It is mounted on the TENANT urlconf, so @login_required alone showed it to
    every parent and student with a session on that host. Every sibling
    tenant-lifecycle surface gates on can_access_tenant_lifecycle; so does this.
    """
    from apps.lifecycle.tenant_school_resolve import require_tenant_lifecycle_school

    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied
    latest = None
    history = []
    alerts = []
    suggestions = []
    if school is not None:
        latest = (
            TenantHealthScore.objects.filter(school=school).order_by("-computed_at").first()
        )
        history = list(
            TenantHealthScore.objects.filter(school=school).order_by("-computed_at")[:12]
        )
        alerts = list(
            TenantRiskAlert.objects.filter(school=school).order_by("-created_at")[:10]
        )
        suggestions = list(
            TenantInterventionSuggestion.objects.filter(school=school).order_by("-created_at")[:10]
        )
    return render(
        request,
        "customersuccess/tenant_health_dashboard.html",
        {
            "school": school,
            "latest": latest,
            "history": history,
            "alerts": alerts,
            "suggestions": suggestions,
        },
    )
