"""
Security & Identity Powerhouse API (plan 3.13–3.23).
Strength, audit feed, export (MFA-gated), lockdown.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.security_health import (
    calculate_profile_strength,
    get_missing_tasks,
    get_security_grace_period_days,
    is_within_grace_period,
)
from apps.accounts.security_audit import lockdown_user_account, log_security_event
from apps.accounts.models import SecurityAuditLog


@login_required
@require_GET
def api_security_strength(request):
    """
    GET /api/me/security-strength/ or profile/security/strength/
    Returns { strength, missing_tasks, grace_period, within_grace_period }.
    """
    user = request.user
    school = getattr(request, "school", None)
    strength = calculate_profile_strength(user, school=school, use_cache=True)
    missing = get_missing_tasks(user, school=school)
    grace_days = get_security_grace_period_days(school)
    within_grace = is_within_grace_period(user, school=school)
    return JsonResponse({
        "strength": strength,
        "missing_tasks": missing,
        "grace_period_days": grace_days,
        "within_grace_period": within_grace,
    })


@login_required
@require_GET
def api_security_activity(request):
    """
    GET profile/security/activity/ — last 30 security events for Bento Timeline.
    """
    user = request.user
    school = getattr(request, "school", None)
    limit = min(int(request.GET.get("limit", 30)), 100)
    qs = SecurityAuditLog.objects.filter(user=user).order_by("-created_at")[:limit]
    if school:
        qs = qs.filter(school=school)
    events = []
    for e in qs:
        events.append({
            "id": e.pk,
            "event_type": e.event_type,
            "description": e.get_event_type_display() if hasattr(e, "get_event_type_display") else e.event_type,
            "ip": e.ip_address or "",
            "user_agent": (e.user_agent or "")[:80],
            "location": (e.location_data or {}).get("city") or (e.location_data or {}).get("country") or "Unknown",
            "is_suspicious": e.is_suspicious,
            "timestamp": e.created_at.isoformat(),
            "initiator": e.initiator or "",
        })
    return JsonResponse({"activities": events})


def _user_has_mfa(user) -> bool:
    try:
        from django_otp import user_has_device
        return user_has_device(user, confirmed=True)
    except Exception:
        return False


@login_required
@require_GET
def api_security_export_log(request):
    """
    Export my security log (data portability). MFA-gated (plan 3.23).
    """
    if not _user_has_mfa(request.user):
        return HttpResponseForbidden("MFA required to export security log.")
    user = request.user
    school = getattr(request, "school", None)
    since = timezone.now() - timedelta(days=365)
    qs = SecurityAuditLog.objects.filter(user=user, created_at__gte=since).order_by("-created_at")
    if school:
        qs = qs.filter(school=school)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "event_type", "ip_address", "location", "is_suspicious"])
    for e in qs:
        loc = (e.location_data or {}).get("city") or (e.location_data or {}).get("country") or ""
        w.writerow([e.created_at.isoformat(), e.event_type, e.ip_address or "", loc, e.is_suspicious])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="security-log.csv"'
    log_security_event(user, SecurityAuditLog.EventType.DATA_EXPORT, request=request, school=school)
    return resp


@login_required
@require_POST
def api_security_lockdown(request):
    """
    POST profile/security/lockdown/ — Emergency Lockdown (plan 3.16).
    """
    user = request.user
    if lockdown_user_account(user, request=request, initiator="self"):
        return JsonResponse({"ok": True, "message": "Account locked. Please set a new password on next login."})
    return JsonResponse({"ok": False, "message": "Lockdown cooldown: wait 24 hours or contact admin."}, status=400)
