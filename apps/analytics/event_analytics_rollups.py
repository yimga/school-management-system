"""
Event-scale analytics rollups — Django ORM only, tenant-scoped, allowlisted models.

Pairs with governed datasets in ``governed_query.catalog`` (same tables); does not expose SQL.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.analytics.governed_query.catalog import DATASETS
from apps.analytics.governed_query.executor import _user_can_access
from apps.analytics.governed_query.executor import execute_governed_query


def _series(qs, date_field: str, *, days: int = 14) -> list[dict[str, Any]]:
    since = timezone.now() - timedelta(days=days)
    filt = {f"{date_field}__gte": since}
    rows = (
        qs.filter(**filt)
        .annotate(bucket=TruncDate(date_field))
        .values("bucket")
        .annotate(n=Count("id"))
        .order_by("bucket")
    )
    out = []
    for r in rows:
        b = r.get("bucket")
        out.append({"day": b.isoformat() if hasattr(b, "isoformat") else str(b), "count": r["n"]})
    return out


def build_event_analytics_bundle(*, user, school_id: str | None, days: int = 14) -> dict[str, Any]:
    """
    Aggregate tenant-safe metrics for streaming/event UX cards + charts JSON.
    """
    if not school_id:
        return {"ok": False, "error": "tenant_required"}

    required_sets = (
        "domain_events",
        "platform_events",
        "offline_sync_events",
        "payments",
        "marketplace_installs",
        "funnel_events",
        "workflow_run_logs",
    )
    for ds in required_sets:
        if ds not in DATASETS or not _user_can_access(user, DATASETS[ds]):
            return {"ok": False, "error": "permission_denied"}

    from django.apps import apps

    from apps.automation.workflow_graph_models import WorkflowRunLog
    from apps.events.models import DomainEvent
    from apps.finance.models import Payment
    from apps.platform_runtime.models import OfflineAction, PlatformEventLog

    AppInstallation = apps.get_model("marketplace", "AppInstallation")
    from apps.schools.models import MarketingFunnelEvent

    sid = school_id

    domain_qs = DomainEvent.objects.filter(school_id=sid)
    platform_qs = PlatformEventLog.objects.filter(school_id=str(sid))
    offline_qs = OfflineAction.objects.filter(school_id=sid)
    payment_qs = Payment.objects.filter(school_id=sid)
    install_qs = AppInstallation.objects.filter(school_id=sid)
    funnel_qs = MarketingFunnelEvent.objects.filter(school_id=sid)
    wf_qs = WorkflowRunLog.objects.filter(workflow__school_id=sid)

    bundle = {
        "ok": True,
        "school_id": sid,
        "window_days": days,
        "domain_event_volume": _series(domain_qs, "created_at", days=days),
        "platform_event_volume": _series(platform_qs, "created_at", days=days),
        "offline_sync_volume": _series(offline_qs, "created_at", days=days),
        "payment_event_volume": _series(payment_qs, "created_at", days=days),
        "marketplace_event_volume": _series(install_qs, "installed_at", days=days),
        "funnel_event_volume": _series(funnel_qs, "created_at", days=days),
        "workflow_event_volume": _series(wf_qs, "created_at", days=days),
        "snapshots": {},
    }

    # Point-in-time governed aggregates (ORM-backed catalog)
    snap_specs = (
        ("domain_events_by_type", "domain_events", ["event_type"]),
        ("payments_by_status", "payments", ["status"]),
        ("workflow_by_trigger", "workflow_run_logs", ["trigger_event"]),
        ("marketplace_by_phase", "marketplace_installs", ["install_phase"]),
        ("offline_by_action", "offline_sync_events", ["action_type"]),
        ("funnel_by_type", "funnel_events", ["event_type"]),
    )
    agg = {"fn": "count", "field": "id"}
    for key, ds_id, gb in snap_specs:
        rows, _meta = execute_governed_query(
            user=user,
            school_id=sid,
            dataset_id=ds_id,
            fields=list(DATASETS[ds_id]["fields"])[:6],
            group_by=list(gb),
            aggregate=agg,
            limit=500,
        )
        bundle["snapshots"][key] = rows[:100]

    return bundle


def insight_card_event_analytics_hub() -> dict[str, Any]:
    """Insight stub — caller attaches tenant-specific counts if desired."""
    return {
        "id": "event_analytics_hub",
        "severity": "info",
        "title": "Event-scale analytics",
        "explanation": "Review domain, platform, payments, workflows, offline sync, and marketplace signals over time.",
        "primary_action": {
            "label": "Open event analytics",
            "path": "/analytics/governed/events/",
        },
        "audience": "operators",
        "surfaces": ["school_health"],
    }
