"""
Enterprise security hub: /super/security/ — alerts, audit tails, session visibility (operator).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.models import SecurityAuditLog, User


def _decode_session_user_ids(limit: int = 150):
    """Recent non-expired sessions with resolved user emails (best-effort)."""
    now = timezone.now()
    rows = []
    sessions = (
        Session.objects.filter(expire_date__gte=now).order_by("-expire_date")[:limit]
    )
    for s in sessions:
        uid = None
        email = "—"
        try:
            data = s.get_decoded()
            uid = data.get("_auth_user_id")
            if uid:
                u = User.objects.filter(pk=uid).only("email", "username").first()
                if u:
                    email = getattr(u, "email", "") or getattr(u, "username", "") or str(
                        uid
                    )
        except Exception:
            pass
        rows.append(
            {
                "session_key_prefix": (s.session_key or "")[:8] + "…",
                "expire_date": s.expire_date,
                "user_id": uid,
                "user_label": email,
            }
        )
    return rows


@require_GET
def super_security_hub(request):
    """Primary operator security dashboard: links + recent signals + audit tails."""
    dashboard_url = reverse("super:dashboard")
    surface_url = reverse("super:security_surface_dashboard")

    cutoff_7d = timezone.now() - timedelta(days=7)

    security_events = list(
        SecurityAuditLog.objects.select_related("user", "school")
        .order_by("-created_at")[:80]
    )

    suspicious_security_events = list(
        SecurityAuditLog.objects.filter(
            is_suspicious=True,
            created_at__gte=cutoff_7d,
        )
        .select_related("user", "school")
        .order_by("-created_at")[:60]
    )
    suspicious_count_7d = SecurityAuditLog.objects.filter(
        is_suspicious=True,
        created_at__gte=cutoff_7d,
    ).count()
    impossible_travel_7d = SecurityAuditLog.objects.filter(
        event_type=SecurityAuditLog.EventType.IMPOSSIBLE_TRAVEL,
        created_at__gte=cutoff_7d,
    ).count()

    perm_events = []
    export_events = []
    access_denied_events = []
    approval_events = []
    try:
        from apps.compliance.models_audit import AuditLog

        perm_events = list(
            AuditLog.objects.filter(
                Q(
                    action__in=(
                        AuditLog.Action.PERMISSION_GRANT,
                        AuditLog.Action.PERMISSION_REVOKE,
                    )
                )
                | Q(
                    model_name="SchoolMembership",
                    action=AuditLog.Action.UPDATE,
                )
            )
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        export_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.EXPORT)
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        access_denied_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED)
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        approval_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.APPROVE)
            .select_related("user")
            .order_by("-timestamp")[:25]
        )
    except Exception:
        pass

    session_rows = _decode_session_user_ids(120)

    admin_security_audit_url = None
    admin_auditlog_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_security_audit_url = reverse(
                "admin:accounts_securityauditlog_changelist"
            )
        except Exception:
            pass
        try:
            admin_auditlog_url = reverse("admin:compliance_auditlog_changelist")
        except Exception:
            pass

    return render(
        request,
        "schools/super_security_hub.html",
        {
            "page_title": "Security & audit",
            "dashboard_url": dashboard_url,
            "security_surface_url": surface_url,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "security_events": security_events,
            "suspicious_security_events": suspicious_security_events,
            "suspicious_count_7d": suspicious_count_7d,
            "impossible_travel_7d": impossible_travel_7d,
            "perm_events": perm_events,
            "export_events": export_events,
            "access_denied_events": access_denied_events,
            "approval_events": approval_events,
            "session_rows": session_rows,
            "session_total_hint": Session.objects.filter(
                expire_date__gte=timezone.now()
            ).count(),
            "admin_security_audit_url": admin_security_audit_url,
            "admin_auditlog_url": admin_auditlog_url,
            "enterprise_super_http_audit": getattr(
                settings, "ENTERPRISE_SUPER_HTTP_AUDIT", False
            ),
        },
    )
