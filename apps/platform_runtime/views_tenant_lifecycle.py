"""Operator lifecycle dashboard (platform operators + tenant hub-eligible admins)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.schools.control_plane import user_has_control_plane_access
from apps.schools.models import School


@login_required
def tenant_lifecycle_dashboard(request):
    from apps.platform_runtime.tenant_lifecycle_operator import (
        build_lifecycle_dashboard_context,
    )

    if user_has_control_plane_access(request.user):
        schools = list(
            School.objects.filter(is_active=True).order_by("-last_activity", "-pk")[:400]
        )
        ctx = build_lifecycle_dashboard_context(schools, viewer_scope="platform")
        return render(
            request,
            "platform_runtime/tenant_lifecycle_dashboard.html",
            ctx,
        )

    school = getattr(request, "school", None)
    if tenant_operator_hub_eligible(request.user) and school is not None:
        ctx = build_lifecycle_dashboard_context([school], viewer_scope="tenant")
        return render(
            request,
            "platform_runtime/tenant_lifecycle_dashboard.html",
            ctx,
        )

    return HttpResponseForbidden("Not allowed.")
