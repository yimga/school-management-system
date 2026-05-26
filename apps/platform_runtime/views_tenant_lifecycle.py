"""Operator lifecycle dashboard (platform operators + tenant hub-eligible admins)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.lifecycle.tenant_school_resolve import (
    can_access_tenant_lifecycle,
    resolve_request_school,
)
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

    school = resolve_request_school(request)
    if school is not None and can_access_tenant_lifecycle(request, school):
        ctx = build_lifecycle_dashboard_context([school], viewer_scope="tenant")
        return render(
            request,
            "platform_runtime/tenant_lifecycle_dashboard.html",
            ctx,
        )

    return HttpResponseForbidden("Not allowed.")
