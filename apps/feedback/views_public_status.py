"""Move 4 — public status page.

A single tenant-agnostic page rendering:
  - Last 30 days of shipped ReleaseNote rows
  - Open marketplace incidents (kill-switch flips)
  - Top up-voted FeatureRequest items currently on the roadmap

Public — no auth required.
"""

from __future__ import annotations

from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET


@require_GET
def public_status_page(request):
    shipped = []
    top_requests = []
    incidents = []
    try:
        from apps.feedback.models import FeatureRequest, ReleaseNote

        cutoff = timezone.now() - timedelta(days=30)
        shipped = list(
            ReleaseNote.objects.filter(created_at__gte=cutoff)
            .select_related("roadmap_item")
            .order_by("-created_at")[:25]
        )
        top_requests = list(
            FeatureRequest.objects.filter(
                status__in=["submitted", "triaging", "planned", "in_progress"],
            )
            .order_by("-weighted_score", "-vote_count")[:10]
        )
    except Exception:
        pass

    try:
        from apps.marketplace.models import AppAuditLog

        cutoff = timezone.now() - timedelta(days=7)
        incidents = list(
            AppAuditLog.objects.filter(
                action__in=["kill_switch_on", "suspend", "incident"],
                created_at__gte=cutoff,
            ).order_by("-created_at")[:20]
        )
    except Exception:
        pass

    return render(
        request,
        "feedback/public_status.html",
        {
            "shipped": shipped,
            "top_requests": top_requests,
            "incidents": incidents,
        },
    )


@require_GET
def public_status_json(request):
    """Same data as JSON for status-monitoring tools."""

    payload = {"shipped": [], "incidents": [], "top_requests": []}
    try:
        from apps.feedback.models import FeatureRequest, ReleaseNote

        cutoff = timezone.now() - timedelta(days=30)
        for r in ReleaseNote.objects.filter(created_at__gte=cutoff).order_by("-created_at")[:25]:
            payload["shipped"].append(
                {
                    "title": r.title,
                    "summary": r.summary or "",
                    "at": r.created_at.isoformat(),
                }
            )
        for fr in (
            FeatureRequest.objects.filter(
                status__in=["submitted", "triaging", "planned", "in_progress"]
            ).order_by("-weighted_score", "-vote_count")[:10]
        ):
            payload["top_requests"].append(
                {
                    "title": fr.title,
                    "status": fr.status,
                    "weighted_score": fr.weighted_score,
                    "vote_count": fr.vote_count,
                }
            )
    except Exception:
        pass
    try:
        from apps.marketplace.models import AppAuditLog

        cutoff = timezone.now() - timedelta(days=7)
        for incident in AppAuditLog.objects.filter(
            action__in=["kill_switch_on", "suspend", "incident"], created_at__gte=cutoff
        ).order_by("-created_at")[:20]:
            payload["incidents"].append(
                {
                    "action": incident.action,
                    "at": incident.created_at.isoformat(),
                    "app": getattr(getattr(incident, "app", None), "slug", None),
                }
            )
    except Exception:
        pass
    return JsonResponse(payload)
