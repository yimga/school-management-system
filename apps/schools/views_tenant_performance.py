"""Tenant performance trust dashboard — HTML + JSON for school admins."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from apps.accounts.decorators import permission_required
from apps.accounts.views import _is_admin_user

from apps.observability.tenant_performance import build_tenant_performance_snapshot


def _snapshot_for_request(request):
    school = getattr(request, "school", None)
    return build_tenant_performance_snapshot(school, request=request)


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_GET
def tenant_performance_dashboard(request):
    snapshot = _snapshot_for_request(request)
    return render(
        request,
        "accounts/tenant_performance_dashboard.html",
        {
            "page_title": _("Platform performance"),
            "performance": snapshot,
            "performance_dict": snapshot.as_dict(),
        },
    )


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_GET
def tenant_performance_json(request):
    """GET …/backend/api/performance.json — tenant performance snapshot."""
    snapshot = _snapshot_for_request(request)
    return JsonResponse(snapshot.as_dict())
