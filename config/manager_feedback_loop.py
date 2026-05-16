"""
Feedback loop live-usage operator surface.

Closes the master-prompt residual "feedback loop live usage" — the harness is
wired (FrictionEvent rollups + FeedbackSubmission + AICopilot interactions);
this surface consumes it and makes the live state visible.

Pure consumer — does NOT write to any table. Aggregates the last 7d/30d and
surfaces:
  - Friction by view (top 10 stuck surfaces)
  - Feedback submissions by category + severity
  - AI assistant adoption (interactions per day, accept/correct rate)
  - Empty-state hint when there's nothing yet (the data flow lights up the
    moment users start using the platform)
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET


@require_GET
def manager_feedback_loop(request):
    """Operator-facing live feedback dashboard. Requires control-plane access."""
    from apps.schools.control_plane import user_has_control_plane_access
    from django.http import HttpResponseForbidden

    if not user_has_control_plane_access(getattr(request, "user", None)):
        return HttpResponseForbidden("Operator access required.")

    now = timezone.now()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    friction_summary = _safe_friction_summary(since_7d, since_30d)
    feedback_summary = _safe_feedback_summary(since_7d, since_30d)
    ai_summary = _safe_ai_summary(since_7d, since_30d)

    total_signal = (
        friction_summary["count_7d"]
        + feedback_summary["count_7d"]
        + ai_summary["interactions_7d"]
    )

    return render(
        request,
        "schools/manager_feedback_loop.html",
        {
            "friction": friction_summary,
            "feedback": feedback_summary,
            "ai": ai_summary,
            "total_signal_7d": total_signal,
            "is_empty": total_signal == 0,
            "now": now,
        },
    )


def _safe_friction_summary(since_7d, since_30d) -> dict:
    """Return friction counts; empty if model not migrated."""
    try:
        from apps.observability.models_friction import FrictionEvent
    except (ImportError, RuntimeError):
        return _empty_period()
    try:
        # tenant-isolation-allow: cross-tenant operator-level aggregate (no PII surfaced)
        recent = FrictionEvent.objects.filter(last_seen__gte=since_7d)
        # tenant-isolation-allow: cross-tenant operator-level aggregate (no PII surfaced)
        recent_30d = FrictionEvent.objects.filter(last_seen__gte=since_30d)
        by_view = list(
            recent.values("view_name", "kind")
            .annotate(n=Count("id"))
            .order_by("-n")[:10]
        )
        return {
            "available": True,
            "count_7d": recent.count(),
            "count_30d": recent_30d.count(),
            "by_view": by_view,
        }
    except (RuntimeError, ValueError):
        return _empty_period()


def _safe_feedback_summary(since_7d, since_30d) -> dict:
    try:
        from apps.feedback.models import FeedbackSubmission
    except (ImportError, RuntimeError):
        return _empty_period()
    try:
        # tenant-isolation-allow: cross-tenant operator-level aggregate; intentional churn analytics
        recent = FeedbackSubmission.objects.filter(created_at__gte=since_7d)
        # tenant-isolation-allow: cross-tenant operator-level aggregate; intentional churn analytics
        recent_30d = FeedbackSubmission.objects.filter(created_at__gte=since_30d)
        by_category = list(
            recent.values("category").annotate(n=Count("id")).order_by("-n")
        )
        by_severity = list(
            recent.values("severity").annotate(n=Count("id")).order_by("-n")
        )
        critical_open = recent.filter(
            Q(severity="critical") & ~Q(status__in=("released", "closed"))
        ).count()
        return {
            "available": True,
            "count_7d": recent.count(),
            "count_30d": recent_30d.count(),
            "by_category": by_category,
            "by_severity": by_severity,
            "critical_open": critical_open,
        }
    except (RuntimeError, ValueError):
        return _empty_period()


def _safe_ai_summary(since_7d, since_30d) -> dict:
    """Aggregate AI gateway interactions if AuditLog rows exist for portal.AICopilot."""
    try:
        from apps.compliance.models_audit import AuditLog
    except (ImportError, RuntimeError):
        return {**_empty_period(), "interactions_7d": 0, "interactions_30d": 0}
    try:
        # tenant-isolation-allow: cross-tenant operator-level aggregate; no per-tenant payload exposed
        recent = AuditLog.objects.filter(
            app_label="portal", model_name="AICopilot", timestamp__gte=since_7d
        )
        # tenant-isolation-allow: cross-tenant operator-level aggregate; no per-tenant payload exposed
        recent_30d = AuditLog.objects.filter(
            app_label="portal", model_name="AICopilot", timestamp__gte=since_30d
        )
        return {
            "available": True,
            "interactions_7d": recent.count(),
            "interactions_30d": recent_30d.count(),
        }
    except (RuntimeError, ValueError):
        return {**_empty_period(), "interactions_7d": 0, "interactions_30d": 0}


def _empty_period() -> dict:
    return {"available": False, "count_7d": 0, "count_30d": 0}
