"""
N24 partial: tenant-scoped platform event tail (append-only log visibility for leadership).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.platform_runtime.models import PlatformEventLog
from apps.schools.mixins import require_school


def _activity_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    r = (getattr(user, "role", "") or "").upper()
    return r in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "IT_ADMIN")


@login_required
@require_school
def tenant_activity_log(request):
    """
    Last N platform events for this school (school_id / tenant_id match).
    """
    if not _activity_roles_ok(request.user):
        return HttpResponseForbidden("Not allowed.")
    school = request.school
    sid = str(school.pk)
    tid = sid[:64]
    sid40 = sid[:40]
    qs = (
        PlatformEventLog.objects.filter(
            Q(school_id=sid40) | Q(tenant_id=tid) | Q(school_id=sid[:36])
        )
        .order_by("-created_at")[:150]
    )
    rows = list(qs)
    return render(
        request,
        "accounts/tenant_activity_log.html",
        {
            "school": school,
            "events": rows,
        },
    )
