"""
Security & Identity Powerhouse API (plan 3.13–3.23).
Strength, audit feed, export (MFA-gated), lockdown.
§10.5.4 Trust product: Sessions page (TRUST_PRODUCT_SURFACES.md).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.core.exceptions import SuspiciousOperation
from django.core.signing import BadSignature
from django.db import DatabaseError
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.profile_security_evaluation import (
    evaluate_user_profile_security,
    get_security_posture_review_interval_days,
    record_security_posture_review,
)
from apps.accounts.security_health import invalidate_security_strength_cache
from apps.accounts.security_health import (
    calculate_profile_strength,
    get_missing_tasks,
    get_security_grace_period_days,
    is_within_grace_period,
)
from apps.accounts.security_audit import lockdown_user_account, log_security_event
from apps.accounts.models import SecurityAuditLog

_SECURITY_SESSION_DECODE_ERRORS = (
    ValueError,
    TypeError,
    SuspiciousOperation,
    BadSignature,
)


@login_required
@require_GET
def api_security_strength(request):
    """
    GET /api/me/security-strength/ or profile/security/strength/
    Returns { strength, missing_tasks, grace_period, within_grace_period }.
    """
    user = request.user
    school = getattr(request, "school", None)
    sessions_count = None
    try:
        sessions_count = int(request.GET.get("active_sessions", ""))
    except (TypeError, ValueError):
        pass
    evaluation = evaluate_user_profile_security(
        user, school=school, active_sessions_count=sessions_count
    )
    strength = calculate_profile_strength(user, school=school, use_cache=True)
    missing = get_missing_tasks(user, school=school)
    grace_days = get_security_grace_period_days(school)
    within_grace = is_within_grace_period(user, school=school)
    return JsonResponse(
        {
            "strength": strength,
            "security_score": evaluation["security_score"],
            "profile_completeness": evaluation["profile_completeness"],
            "critical_vulnerabilities": evaluation["critical_vulnerabilities"],
            "ux_optimizations": evaluation["ux_optimizations"],
            "strength_band": evaluation["strength_band"],
            "strength_label": evaluation["strength_label"],
            "missing_tasks": missing,
            "grace_period_days": grace_days,
            "within_grace_period": within_grace,
            "security_posture_review_due": evaluation.get("security_posture_review_due"),
            "days_until_posture_review": evaluation.get("days_until_posture_review"),
            "minimum_score_for_role": evaluation.get("minimum_score_for_role"),
        }
    )


@login_required
@require_GET
def api_security_activity(request):
    """
    GET profile/security/activity/ — last 30 security events for Bento Timeline.
    """
    user = request.user
    school = getattr(request, "school", None)
    limit = min(int(request.GET.get("limit", 30)), 100)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = SecurityAuditLog.objects.filter(user=user)
    if school:
        qs = qs.filter(school=school)
    qs = qs.order_by("-created_at")[:limit]
    events = []
    for e in qs:
        events.append(
            {
                "id": e.pk,
                "event_type": e.event_type,
                "description": e.get_event_type_display()
                if hasattr(e, "get_event_type_display")
                else e.event_type,
                "ip": e.ip_address or "",
                "user_agent": (e.user_agent or "")[:80],
                "location": (e.location_data or {}).get("city")
                or (e.location_data or {}).get("country")
                or "Unknown",
                "is_suspicious": e.is_suspicious,
                "timestamp": e.created_at.isoformat(),
                "initiator": e.initiator or "",
            }
        )
    return JsonResponse({"activities": events})


def _user_has_mfa(user) -> bool:
    try:
        from django_otp import user_has_device

        try:
            has_device = user_has_device(user, confirmed=True)
        except TypeError:
            has_device = user_has_device(user)
        if has_device:
            return True
    except (ImportError, AttributeError, TypeError):
        pass
    try:
        from apps.accounts.models import UserPasskey

        return UserPasskey.objects.filter(user=user).exists()
    except (ImportError, AttributeError, TypeError):
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
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    since = timezone.now() - timedelta(days=365)
    qs = SecurityAuditLog.objects.filter(user=user, created_at__gte=since).order_by(
        "-created_at"
    )
    if school:
        qs = qs.filter(school=school)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "event_type", "ip_address", "location", "is_suspicious"])
    for e in qs:
        loc = (
            (e.location_data or {}).get("city")
            or (e.location_data or {}).get("country")
            or ""
        )
        w.writerow(
            [
                e.created_at.isoformat(),
                e.event_type,
                e.ip_address or "",
                loc,
                e.is_suspicious,
            ]
        )
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="security-log.csv"'
    log_security_event(
        user, SecurityAuditLog.EventType.DATA_EXPORT, request=request, school=school
    )
    return resp


@login_required
@require_POST
def api_security_lockdown(request):
    """
    POST profile/security/lockdown/ — Emergency Lockdown (plan 3.16).
    """
    user = request.user
    if lockdown_user_account(user, request=request, initiator="self"):
        return JsonResponse(
            {
                "ok": True,
                "message": "Account locked. Please set a new password on next login.",
            }
        )
    return JsonResponse(
        {"ok": False, "message": "Lockdown cooldown: wait 24 hours or contact admin."},
        status=400,
    )


def _sessions_for_user(user, limit=50):
    """Return list of Session objects belonging to this user (decode session_data for _auth_user_id)."""
    user_pk_str = str(user.pk)
    out = []
    for session in Session.objects.order_by("-expire_date")[: limit * 2]:
        if len(out) >= limit:
            break
        try:
            data = session.get_decoded()
            if data.get("_auth_user_id") == user_pk_str:
                out.append(session)
        except _SECURITY_SESSION_DECODE_ERRORS:
            continue
    return out


@login_required
@require_GET
def sessions_page(request):
    """
    §10.5.4 Trust product: Sessions & devices page (TRUST_PRODUCT_SURFACES.md).
    Lists active sessions for the current user; supports revoke.
    """
    sessions = _sessions_for_user(request.user)
    current_session_key = request.session.session_key
    session_list = []
    for s in sessions:
        try:
            data = s.get_decoded()
            user_agent = (data.get("_auth_user_backend") or "")[:80]
            # Django session often has no user_agent in data; we don't store it by default
            session_list.append(
                {
                    "session_key": s.session_key,
                    "expire_date": s.expire_date,
                    "is_current": s.session_key == current_session_key,
                    "user_agent": user_agent or "—",
                }
            )
        except _SECURITY_SESSION_DECODE_ERRORS:
            session_list.append(
                {
                    "session_key": s.session_key,
                    "expire_date": s.expire_date,
                    "is_current": s.session_key == current_session_key,
                    "user_agent": "—",
                }
            )
    return render(
        request,
        "accounts/sessions_page.html",
        {"sessions": session_list, "current_session_key": current_session_key},
    )


@login_required
@require_POST
def sessions_revoke(request, session_key):
    """
    Revoke a session (delete + audit). §10.5.4 Trust product.
    User can revoke any of their own sessions except the current one (to avoid locking themselves out).
    """
    if request.session.session_key == session_key:
        return JsonResponse(
            {"ok": False, "message": "Cannot revoke current session."},
            status=400,
        )
    user_pk_str = str(request.user.pk)
    session = Session.objects.filter(session_key=session_key).first()
    if not session:
        return JsonResponse({"ok": False, "message": "Session not found."}, status=404)
    try:
        data = session.get_decoded()
        if data.get("_auth_user_id") != user_pk_str:
            return HttpResponseForbidden("Not your session.")
    except _SECURITY_SESSION_DECODE_ERRORS:
        return HttpResponseForbidden("Invalid session.")
    session.delete()
    school = getattr(request, "school", None)
    log_security_event(
        request.user,
        SecurityAuditLog.EventType.SESSION_REVOKED,
        request=request,
        school=school,
    )
    if (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.GET.get("format") == "json"
    ):
        return JsonResponse({"ok": True})
    return redirect("accounts:sessions_page")


@login_required
def security_posture_review(request):
    """
    Quarterly security posture check-in for every user (default every 90 days).
    GET: review dashboard; POST: acknowledge completion.
    """
    from django.utils.http import url_has_allowed_host_and_scheme
    from django.utils.translation import gettext as _

    from apps.accounts.operator_account_render import render_account_page

    school = getattr(request, "school", None)
    user = request.user
    if request.method == "POST":
        record_security_posture_review(user)
        invalidate_security_strength_cache(user, school)
        request.session.pop("security_posture_review_nagged", None)
        from apps.accounts.security_posture_notifications import (
            POSTURE_NOTIFICATION_TITLE,
            clear_corner_snooze,
        )

        clear_corner_snooze(request)
        try:
            from apps.finance.models import Notification

            # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
            Notification.objects.filter(
                recipient=user,
                title=POSTURE_NOTIFICATION_TITLE,
                is_read=False,
            ).update(is_read=True)
        except (DatabaseError, ImportError, AttributeError, TypeError):
            pass
        log_security_event(
            user,
            SecurityAuditLog.EventType.PWD_RESET,
            request=request,
            school=school,
        )
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}
        ):
            return redirect(next_url)
        return redirect("accounts:user_profile")

    evaluation = evaluate_user_profile_security(user, school=school)
    interval_days = get_security_posture_review_interval_days(school)
    context = {
        "profile_security": evaluation,
        "posture_review_interval_days": interval_days,
        "next_url": request.GET.get("next", ""),
    }
    return render_account_page(
        request,
        portal_template="accounts/security_posture_review.html",
        body_template="accounts/partials/operator_security_posture_review_body.html",
        context=context,
        page_title=_("Security posture review"),
    )


@login_required
@require_POST
def security_posture_session_modal_ack(request):
    from apps.accounts.security_posture_notifications import acknowledge_session_modal

    acknowledge_session_modal(request)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def notification_corner_snooze(request):
    from apps.accounts.security_posture_notifications import snooze_corner_notifications

    snooze_corner_notifications(request)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def notification_corner_dismiss(request):
    from apps.accounts.security_posture_notifications import POSTURE_NOTIFICATION_TITLE

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
    notification_id = body.get("notification_id")
    try:
        from apps.finance.models import Notification
        from apps.schools.portal_ready_corner_notifications import (
            mark_portal_ready_corner_dismissed,
        )

        # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
        qs = Notification.objects.filter(recipient=request.user, is_read=False)
        if notification_id:
            qs = qs.filter(pk=notification_id)
            mark_portal_ready_corner_dismissed(request, str(notification_id))
        else:
            qs = qs.filter(title=POSTURE_NOTIFICATION_TITLE)
        qs.update(is_read=True)
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        pass
    return JsonResponse({"ok": True})


@login_required
@require_POST
def notification_corner_mark_read(request):
    from apps.accounts.security_posture_notifications import POSTURE_NOTIFICATION_TITLE
    from apps.schools.portal_ready_corner_notifications import (
        mark_portal_ready_corner_dismissed,
    )

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
    notification_id = body.get("notification_id")
    try:
        from apps.finance.models import Notification

        # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
        qs = Notification.objects.filter(recipient=request.user, is_read=False)
        if notification_id:
            qs = qs.filter(pk=notification_id)
            mark_portal_ready_corner_dismissed(request, str(notification_id))
        else:
            qs = qs.filter(title=POSTURE_NOTIFICATION_TITLE)
        updated = qs.update(is_read=True)
        if notification_id and updated:
            mark_portal_ready_corner_dismissed(request, str(notification_id))
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        pass
    return JsonResponse({"ok": True})
