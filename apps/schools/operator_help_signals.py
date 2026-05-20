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
    deflection = safe_deflection_summary(since_7d, since_30d)
    kb = safe_kb_catalog_summary()
    zero_results = safe_zero_result_summary(since_7d)
    deflection_metrics = safe_deflection_metrics(since_7d)
    proactive = safe_proactive_friction_nudges(since_7d)
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
        "deflection": deflection,
        "deflection_metrics": deflection_metrics,
        "zero_results": zero_results,
        "proactive": proactive,
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

        from apps.feedback.db_readiness import feedback_schema_ready
        from apps.feedback.models import FeedbackSubmission
    except (ImportError, RuntimeError):
        return {**_empty_period(), "critical_open": 0}
    if not feedback_schema_ready():
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


def safe_deflection_summary(since_7d, since_30d) -> dict:
    try:
        from django.db.models import Count

        from apps.feedback.models import SupportDeflectionEvent, SupportAIInteractionReview
    except (ImportError, RuntimeError):
        return {**_empty_period(), "pending_reviews": 0}
    try:
        # tenant-isolation-allow: cross-tenant operator aggregate; fingerprint-only telemetry
        recent = SupportDeflectionEvent.objects.filter(created_at__gte=since_7d)
        recent_30d = SupportDeflectionEvent.objects.filter(created_at__gte=since_30d)
        by_outcome = list(
            recent.values("outcome").annotate(n=Count("id")).order_by("-n")
        )
        pending_reviews = SupportAIInteractionReview.objects.filter(
            status=SupportAIInteractionReview.Status.PENDING
        ).count()
        return {
            "available": True,
            "count_7d": recent.count(),
            "count_30d": recent_30d.count(),
            "by_outcome": by_outcome,
            "pending_reviews": pending_reviews,
        }
    except Exception:
        return {**_empty_period(), "pending_reviews": 0}


def safe_kb_catalog_summary() -> dict:
    try:
        from apps.portal.kb_context import filter_kb_articles_for_host, published_kb_queryset
        from apps.portal.models_kb import KBCategory
    except (ImportError, RuntimeError):
        return {"available": False, "article_count": 0, "category_count": 0, "featured": []}
    try:
        base = filter_kb_articles_for_host(
            published_kb_queryset(),
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


def safe_zero_result_summary(since_7d) -> dict:
    try:
        from apps.portal.help_search_intelligence import zero_result_fingerprints

        rows = zero_result_fingerprints(days=7, limit=8)
        return {"available": True, "top": rows, "count_7d": sum(r.get("count", 0) for r in rows)}
    except Exception:
        return {"available": False, "top": [], "count_7d": 0}


def safe_deflection_metrics(since_7d) -> dict:
    try:
        from apps.portal.help_search_intelligence import deflection_rate_summary

        return deflection_rate_summary(days=7)
    except Exception:
        return {"available": False}


def safe_proactive_friction_nudges(since_7d) -> dict:
    """Map friction hotspots to KB search CTAs (batch 1342)."""
    friction = safe_friction_summary(since_7d, since_7d)
    if not friction.get("available"):
        return {"available": False, "nudges": []}
    try:
        from django.urls import reverse

        nudges = []
        for row in friction.get("by_view") or []:
            view_name = (row.get("view_name") or "").strip()
            if not view_name:
                continue
            q = view_name.replace("_", " ").replace(".", " ")
            nudges.append(
                {
                    "view_name": view_name,
                    "count": row.get("n", 0),
                    "kind": row.get("kind", ""),
                    "kb_search_url": reverse("kb:kb_search") + f"?q={q}",
                }
            )
        return {"available": True, "nudges": nudges[:5]}
    except Exception:
        return {"available": False, "nudges": []}


def _empty_period() -> dict:
    return {
        "available": False,
        "count_7d": 0,
        "count_30d": 0,
        "by_view": [],
        "by_category": [],
        "critical_open": 0,
    }
