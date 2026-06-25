"""
Tenant-facing performance trust dashboard (T1).

Builds an honest snapshot for school admins: fleet availability for their
tenant, friction rollups as an experience proxy, lifecycle milestones, and
platform SLO *commitments* (targets only — never fabricated live latency).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Daily friction event count at or above this marks the day as degraded.
_FRICTION_DEGRADED_DAILY_THRESHOLD = 5
_TIMELINE_WINDOW_DAYS = 7
_LIFECYCLE_EVENT_LIMIT = 12


@dataclass(frozen=True)
class TenantPerformanceSnapshot:
    """Immutable snapshot returned to templates and JSON consumers."""

    generated_at: str
    school_slug: str
    fleet_state: str
    heatmap_tier: str
    availability_tier: str
    availability_label: str
    experience_score_pct: int
    timeline_days: list[dict[str, Any]] = field(default_factory=list)
    friction_summary: dict[str, Any] = field(default_factory=dict)
    platform_commitments: list[dict[str, Any]] = field(default_factory=list)
    lifecycle_events: list[dict[str, Any]] = field(default_factory=list)
    operational_health: dict[str, Any] = field(default_factory=dict)
    public_status_url: str = ""
    revision: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "school_slug": self.school_slug,
            "fleet_state": self.fleet_state,
            "heatmap_tier": self.heatmap_tier,
            "availability_tier": self.availability_tier,
            "availability_label": self.availability_label,
            "experience_score_pct": self.experience_score_pct,
            "timeline_days": self.timeline_days,
            "friction_summary": self.friction_summary,
            "platform_commitments": self.platform_commitments,
            "lifecycle_events": self.lifecycle_events,
            "operational_health": self.operational_health,
            "public_status_url": self.public_status_url,
            "revision": self.revision,
        }


def _public_status_url() -> str:
    base = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}/status/"
    return "/status/"


def _fleet_to_availability(heatmap: str, fleet_state: str) -> tuple[str, str]:
    if heatmap in ("danger", "idle") or fleet_state in (
        "suspended",
        "provision_error",
        "inactive",
        "offboarding",
        "wind_down",
    ):
        return "down", str(_("Service interrupted"))
    if heatmap == "warn" or fleet_state in ("pending_approval", "provisioning", "billing_exception"):
        return "degraded", str(_("Attention needed"))
    return "up", str(_("Operational"))


def _day_tier(
    *,
    friction_count: int,
    had_incident: bool,
) -> str:
    if had_incident:
        return "down"
    if friction_count >= _FRICTION_DEGRADED_DAILY_THRESHOLD:
        return "degraded"
    return "up"


def _friction_rollups(school, *, since: date) -> tuple[dict[date, int], dict[str, Any]]:
    summary: dict[str, Any] = {
        "total_7d": 0,
        "by_kind": {},
        "top_views": [],
    }
    daily: dict[date, int] = {}
    if school is None:
        return daily, summary

    try:
        from apps.observability.models_friction import FrictionEvent

        qs = FrictionEvent.objects.filter(school=school, utc_day__gte=since)
        summary["total_7d"] = int(qs.aggregate(total=Sum("count"))["total"] or 0)

        for row in qs.values("kind").annotate(events=Sum("count")).order_by("-events"):
            summary["by_kind"][row["kind"]] = int(row["events"] or 0)

        for row in (
            qs.values("view_name")
            .annotate(events=Sum("count"))
            .order_by("-events")[:5]
        ):
            summary["top_views"].append(
                {"view_name": row["view_name"], "events": int(row["events"] or 0)}
            )

        for row in qs.values("utc_day").annotate(events=Sum("count")):
            day_val = row["utc_day"]
            if isinstance(day_val, date):
                daily[day_val] = int(row["events"] or 0)
    except Exception:  # noqa: BLE001
        logger.debug("tenant_performance: friction rollup unavailable", exc_info=True)

    return daily, summary


def _incident_days(school, *, since: date) -> set[date]:
    days: set[date] = set()
    if school is None:
        return days
    try:
        from apps.schools.models import SchoolProvisioningEvent

        incident_types = {
            SchoolProvisioningEvent.EventType.FAILED,
            SchoolProvisioningEvent.EventType.OFFBOARDING_DEACTIVATED,
            SchoolProvisioningEvent.EventType.OFFBOARDING_PURGE_COMPLETED,
        }
        for row in (
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type__in=incident_types,
                created_at__date__gte=since,
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
        ):
            day_val = row["day"]
            if isinstance(day_val, date):
                days.add(day_val)
    except Exception:  # noqa: BLE001
        logger.debug("tenant_performance: lifecycle incidents unavailable", exc_info=True)
    return days


def _lifecycle_events(school, *, since: date) -> list[dict[str, Any]]:
    if school is None:
        return []
    try:
        from apps.schools.models import SchoolProvisioningEvent

        rows = []
        for ev in (
            SchoolProvisioningEvent.objects.filter(school=school, created_at__date__gte=since)
            .order_by("-created_at")[:_LIFECYCLE_EVENT_LIMIT]
        ):
            rows.append(
                {
                    "event_type": ev.event_type,
                    "label": ev.get_event_type_display(),
                    "created_at": ev.created_at.isoformat(),
                }
            )
        return rows
    except Exception:  # noqa: BLE001
        logger.debug("tenant_performance: lifecycle events unavailable", exc_info=True)
        return []


def _experience_score(total_friction: int) -> int:
    """Honest proxy: fewer friction rollups → higher score (not latency)."""
    if total_friction <= 0:
        return 100
    penalty = min(40, total_friction // 2)
    return max(60, 100 - penalty)


def build_tenant_performance_snapshot(
    school,
    *,
    request=None,
    window_days: int = _TIMELINE_WINDOW_DAYS,
) -> TenantPerformanceSnapshot:
    """Build the tenant performance trust snapshot."""
    now = timezone.now()
    today = now.date()
    since = today - timedelta(days=max(1, window_days) - 1)

    fleet_state = ""
    heatmap = "warn"
    if school is not None:
        try:
            from apps.schools.fleet_status import resolve_school_fleet_status

            fleet = resolve_school_fleet_status(school)
            fleet_state = str(fleet.get("fleet_state") or "")
            heatmap = str(fleet.get("heatmap_tier") or "warn")
        except Exception:  # noqa: BLE001
            logger.debug("tenant_performance: fleet status unavailable", exc_info=True)

    availability_tier, availability_label = _fleet_to_availability(heatmap, fleet_state)

    daily_friction, friction_summary = _friction_rollups(school, since=since)
    incident_days = _incident_days(school, since=since)

    timeline_days: list[dict[str, Any]] = []
    for offset in range(window_days - 1, -1, -1):
        day = today - timedelta(days=offset)
        friction_count = daily_friction.get(day, 0)
        tier = _day_tier(friction_count=friction_count, had_incident=(day in incident_days))
        timeline_days.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%a %b %d").replace(" 0", " ") if hasattr(day, "strftime") else str(day),
                "tier": tier,
                "friction_events": friction_count,
            }
        )

    commitments: list[dict[str, Any]] = []
    try:
        from apps.observability.slo import slo_commitments_for_display

        tenant_relevant = {
            "portal.dashboard",
            "portal.gradebook",
            "finance.payment.record",
            "auth.login",
            "api.public_config",
            "ui.friction.validation_retry",
        }
        commitments = [
            row for row in slo_commitments_for_display() if row.get("key") in tenant_relevant
        ]
        if not commitments:
            commitments = slo_commitments_for_display()[:6]
    except Exception:  # noqa: BLE001
        commitments = []

    operational_health: dict[str, Any] = {}
    if school is not None:
        try:
            from apps.schools.tenant_operational_health import resolve_tenant_operational_health

            operational_health = resolve_tenant_operational_health(
                school, request=request, surface="admin"
            )
        except Exception:  # noqa: BLE001
            operational_health = {}
        try:
            from apps.schools.school_readiness import build_school_readiness

            readiness = build_school_readiness(school)
            operational_health = dict(operational_health or {})
            operational_health["provisioning_slo"] = readiness.get("provisioning_slo") or {}
        except Exception:  # noqa: BLE001
            pass

    slug = getattr(school, "slug", "") or ""
    payload_core = {
        "availability_tier": availability_tier,
        "experience_score_pct": _experience_score(int(friction_summary.get("total_7d") or 0)),
        "timeline_days": timeline_days,
        "friction_total": friction_summary.get("total_7d"),
    }
    revision = hashlib.sha256(
        json.dumps(payload_core, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    return TenantPerformanceSnapshot(
        generated_at=now.isoformat(),
        school_slug=slug,
        fleet_state=fleet_state,
        heatmap_tier=heatmap,
        availability_tier=availability_tier,
        availability_label=availability_label,
        experience_score_pct=_experience_score(int(friction_summary.get("total_7d") or 0)),
        timeline_days=timeline_days,
        friction_summary=friction_summary,
        platform_commitments=commitments,
        lifecycle_events=_lifecycle_events(school, since=since),
        operational_health=operational_health,
        public_status_url=_public_status_url(),
        revision=revision,
    )
