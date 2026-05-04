"""Honest operator adoption metrics from platform + funnel events (no fabricated rates)."""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.platform_runtime.models import PlatformEventLog


def _impl_url() -> str:
    try:
        return reverse("platform_runtime:implementation_command_center")
    except NoReverseMatch:
        return ""


def _lifecycle_url() -> str:
    try:
        return reverse("platform_runtime:tenant_lifecycle_dashboard")
    except NoReverseMatch:
        return ""


def _funnel_ttftv_hours_single_school(school_id) -> float | None:
    """Median-style single path: first onboarding_start → first_action, if both exist."""
    try:
        from apps.schools.models import MarketingFunnelEvent, School

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return None
        start = (
            MarketingFunnelEvent.objects.filter(
                school=school, event_type="onboarding_start"
            )
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        fa = (
            MarketingFunnelEvent.objects.filter(
                school=school, event_type="first_action"
            )
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        if start and fa:
            return round((fa - start).total_seconds() / 3600.0, 2)
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        pass
    return None


def compute_operator_adoption_metrics(school_ids: list) -> dict[str, Any]:
    """
    Aggregate coarse signals when *school_ids* non-empty.

    Uses explicit surface-view events when present; substring match is fallback only.
    """
    if not school_ids:
        return {
            "insufficient_data": True,
            "reason": "No school scope for metrics.",
            "blockers": [
                {
                    "label": "Select a tenant",
                    "primary_action": {
                        "label": "Lifecycle dashboard",
                        "url": _lifecycle_url(),
                    },
                }
            ],
        }

    sid_set = {str(x) for x in school_ids if x is not None}
    base = PlatformEventLog.objects.filter(school_id__in=sid_set)
    total = base.count()
    if total == 0:
        return {
            "insufficient_data": True,
            "reason": "No PlatformEventLog rows for this scope yet.",
            "blockers": [
                {
                    "label": "Emit or replay platform events for this tenant",
                    "primary_action": {
                        "label": "Implementation command center",
                        "url": _impl_url(),
                    },
                }
            ],
            "dashboard_viewed": False,
            "first_action_completed": False,
            "workflow_used": False,
            "report_generated": False,
            "parent_portal_activated": False,
            "offline_sync_used": False,
            "payment_readiness_viewed": False,
            "support_playbook_viewed": False,
            "implementation_center_viewed": False,
            "unresolved_blockers": 0,
            "time_to_first_value_hours": None,
            "time_to_first_value_insufficient_data": True,
        }

    def has_exact(et: str) -> bool:
        return base.filter(event_type=et).exists()

    def has_substr(sub: str) -> bool:
        return base.filter(event_type__icontains=sub).exists()

    ttftv: float | None = None
    ttftv_insufficient = True
    if len(school_ids) == 1:
        ttftv = _funnel_ttftv_hours_single_school(school_ids[0])
        ttftv_insufficient = ttftv is None
    else:
        ttftv_insufficient = True

    metrics = {
        "insufficient_data": False,
        "reason": "",
        "implementation_center_viewed": has_exact("implementation_command_center_viewed")
        or has_substr("implementation_command_center"),
        "dashboard_viewed": has_exact("tenant_dashboard_viewed")
        or has_substr("dashboard")
        or has_substr("lifecycle"),
        "first_action_completed": has_substr("first_action"),
        "workflow_used": has_exact("workflow_completed")
        or has_substr("workflow")
        or has_substr("automation"),
        "report_generated": has_substr("report"),
        "parent_portal_activated": has_substr("parent") or has_substr("portal"),
        "offline_sync_used": has_substr("offline"),
        "payment_readiness_viewed": has_substr("payment") or has_substr("finance"),
        "support_playbook_viewed": has_exact("support_playbook_center_viewed")
        or has_substr("playbook"),
        "unresolved_blockers": 0,
        "time_to_first_value_hours": ttftv,
        "time_to_first_value_insufficient_data": ttftv_insufficient,
        "event_sample_size": total,
        "computed_at": timezone.now().isoformat(),
    }
    metrics["blockers"] = []
    if not metrics["first_action_completed"]:
        metrics["blockers"].append(
            {
                "label": "First action not observed in platform event log for this scope",
                "primary_action": {
                    "label": "Complete onboarding checklist",
                    "url": _impl_url(),
                },
            }
        )
    return metrics
