"""
Cross-tenant operator help signals (aggregates only — no PII).

Shared by Help Center hub and Feedback loop dashboard.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


def operator_help_signal_bundle(*, days_7: int = 7, days_30: int = 30) -> dict:
    now = timezone.now()
    since_7d = now - timedelta(days=days_7)
    since_30d = now - timedelta(days=days_30)
    friction = safe_friction_summary(since_7d, since_30d)
    feedback = safe_feedback_summary(since_7d, since_30d)
    ai = safe_ai_summary(since_7d, since_30d)
    kb = safe_kb_catalog_summary()
    total_signal_7d = (
        friction["count_7d"]
        + feedback["count_7d"]
        + ai.get("interactions_7d", 0)
    )
    return {
        "now": now,
        "friction": friction,
        "feedback": feedback,
        "ai": ai,
        "kb": kb,
        "total_signal_7d": total_signal_7d,
        "is_empty": total_signal_7d == 0 and not kb.get("article_count"),
    }


def safe_friction_summary(since_7d, since_30d) -> dict:
    try:
        from django.db.models import Count

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
    except Exception:
        return _empty_period()


def safe_feedback_summary(since_7d, since_30d) -> dict:
    try:
        from django.db.models import Count, Q

        from apps.feedback.models import FeedbackSubmission
    except (ImportError, RuntimeError):
        return {**_empty_period(), "critical_open": 0}
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
    except Exception:
        return {**_empty_period(), "critical_open": 0}


def safe_ai_summary(since_7d, since_30d) -> dict:
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
    except Exception:
        return {**_empty_period(), "interactions_7d": 0, "interactions_30d": 0}


def safe_kb_catalog_summary() -> dict:
    try:
        from apps.portal.kb_context import filter_kb_articles_for_host
        from apps.portal.models_kb import KBArticle, KBCategory
    except (ImportError, RuntimeError):
        return {"available": False, "article_count": 0, "category_count": 0, "featured": []}
    try:
        base = filter_kb_articles_for_host(
            KBArticle.objects.filter(status="PUBLISHED"),
            is_operator=True,
        )
        categories = KBCategory.objects.filter(is_active=True)
        featured = list(
            base.filter(is_featured=True).order_by("-view_count")[:3].values(
                "title", "slug", "summary"
            )
        )
        return {
            "available": True,
            "article_count": base.count(),
            "category_count": categories.count(),
            "featured": featured,
        }
    except Exception:
        return {"available": False, "article_count": 0, "category_count": 0, "featured": []}


def _empty_period() -> dict:
    return {
        "available": False,
        "count_7d": 0,
        "count_30d": 0,
        "by_view": [],
        "by_category": [],
        "critical_open": 0,
    }
