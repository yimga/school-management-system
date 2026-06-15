"""
Unified fleet status for operator monitoring surfaces.

Single resolver used by:
  - Tenants · health grid (cockpit heatmap)
  - Platform pulse Schools card
  - /super/api/cockpit/live.json and /super/api/fleet/live.json
  - CSV/PDF fleet exports
  - Tenant health monitor rows

Maps lifecycle + provisioning + billing signals to a canonical fleet_state
and a heatmap color tier (healthy | okay | warn | danger | idle).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.billing.models import TenantSubscription
from apps.schools.control_plane_lifecycle import (
    batch_current_subscriptions,
    get_lifecycle_snapshot,
)
from apps.schools.models import School, SchoolProvisioningEvent

logger = logging.getLogger(__name__)

# Distinguishes "caller omitted cached_subscription → look it up" from an
# explicit ``None`` ("batch caller resolved it; this school genuinely has no
# subscription"). Conflating the two masked billing_exception on single-school
# surfaces — see resolve_school_fleet_status.
_SUBSCRIPTION_UNSET = object()

FLEET_POLL_INTERVAL_SECONDS = 15

# Short-TTL cache for the request-invariant fleet poller payload (the cockpit
# live poll hits this every FLEET_POLL_INTERVAL_SECONDS from every operator tab).
# TTL = one poll interval bounds staleness to a single poll the client already
# makes. invalidate_fleet_status_cache() busts it on lifecycle mutations.
FLEET_STATUS_CACHE_KEY = "rmc:fleet:status:v1"

FLEET_STATE_LIVE = "live"
FLEET_STATE_TRIALING = "trialing"
FLEET_STATE_PENDING = "pending_approval"
FLEET_STATE_PROVISIONING = "provisioning"
FLEET_STATE_PROVISION_ERROR = "provision_error"
FLEET_STATE_SUSPENDED = "suspended"
FLEET_STATE_BILLING = "billing_exception"
FLEET_STATE_INACTIVE = "inactive"
FLEET_STATE_WIND_DOWN = "wind_down"
FLEET_STATE_OFFBOARDING = "offboarding"

HEATMAP_TIERS = ("healthy", "okay", "warn", "danger", "idle")

_FLEET_TO_HEATMAP: dict[str, str] = {
    FLEET_STATE_LIVE: "healthy",
    FLEET_STATE_TRIALING: "okay",
    FLEET_STATE_PENDING: "warn",
    FLEET_STATE_PROVISIONING: "warn",
    FLEET_STATE_PROVISION_ERROR: "danger",
    FLEET_STATE_SUSPENDED: "danger",
    FLEET_STATE_BILLING: "danger",
    FLEET_STATE_WIND_DOWN: "danger",
    FLEET_STATE_OFFBOARDING: "danger",
    FLEET_STATE_INACTIVE: "idle",
}

_IN_FLIGHT_TYPES = frozenset(
    {
        SchoolProvisioningEvent.EventType.QUEUED,
        SchoolProvisioningEvent.EventType.STARTED,
        SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
    }
)


def _latest_event_subquery():
    return SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )


def build_fleet_queryset():
    """All schools with provisioning + subscription annotations for fleet status."""
    latest_event = _latest_event_subquery()
    latest_sub = TenantSubscription.objects.filter(school_id=OuterRef("pk")).order_by(
        "-updated_at", "-created_at"
    )
    return (
        # select_related the reverse OneToOne billing_account: get_lifecycle_snapshot
        # falls back to school.billing_account for any school without a current
        # subscription (new / pending schools especially), which is one query per
        # such school across the up-to-500-tile fleet loop. Reverse OneToOne is
        # select_related-safe (unlike a reverse FK); an absent row caches a
        # DoesNotExist that get_lifecycle_snapshot already catches — no extra query.
        School.objects.select_related("billing_account")
        .annotate(
            latest_event_type=Subquery(latest_event.values("event_type")[:1]),
            latest_event_status=Subquery(latest_event.values("status")[:1]),
            latest_subscription_status=Subquery(latest_sub.values("status")[:1]),
        )
        .order_by("-is_active", "name")
    )


def _wind_down_active(school) -> bool:
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return False
    off = settings.get("offboarding") or {}
    if not isinstance(off, dict):
        return False
    if off.get("wind_down_mode"):
        return True
    self_status = str(off.get("self_service_status") or "").strip()
    return self_status in ("closure_requested", "scheduled")


def _provisioning_in_flight(school) -> bool:
    event_type = getattr(school, "latest_event_type", None)
    event_status = getattr(school, "latest_event_status", None)
    if not event_type:
        return False
    if event_type in _IN_FLIGHT_TYPES and event_status != SchoolProvisioningEvent.Status.ERROR:
        return not SchoolProvisioningEvent.objects.filter(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.COMPLETED,
        ).exists()
    return False


def _provision_error(school) -> bool:
    if getattr(school, "latest_event_status", None) == SchoolProvisioningEvent.Status.ERROR:
        return True
    return getattr(school, "latest_event_type", None) == SchoolProvisioningEvent.EventType.FAILED


def resolve_school_fleet_status(
    school,
    *,
    cached_subscription=_SUBSCRIPTION_UNSET,
) -> dict[str, Any]:
    """Return canonical fleet status for one school.

    When ``cached_subscription`` is omitted, the current subscription is looked
    up so single-school callers get correct billing_exception detection. Batch
    callers pass the pre-resolved row (or ``None`` for a genuinely sub-less
    school) to skip the per-school query. NOTE: a bare ``None`` default would
    be wrong here — get_lifecycle_snapshot treats ``None`` as "no subscription"
    (its own sentinel means "look it up"), so defaulting to ``None`` silently
    masked PAST_DUE / SUSPENDED schools as "live" on single-school surfaces.
    """
    if cached_subscription is _SUBSCRIPTION_UNSET:
        lifecycle = get_lifecycle_snapshot(school)
    else:
        lifecycle = get_lifecycle_snapshot(school, cached_subscription=cached_subscription)
    lifecycle_state = lifecycle.get("state") or FLEET_STATE_INACTIVE

    fleet_state = FLEET_STATE_LIVE
    if not getattr(school, "is_active", False):
        fleet_state = FLEET_STATE_INACTIVE
    elif getattr(school, "is_frozen", False):
        fleet_state = FLEET_STATE_SUSPENDED
    elif _provision_error(school):
        fleet_state = FLEET_STATE_PROVISION_ERROR
    elif _provisioning_in_flight(school):
        fleet_state = FLEET_STATE_PROVISIONING
    elif _wind_down_active(school):
        fleet_state = FLEET_STATE_WIND_DOWN
    elif not getattr(school, "is_approved", True):
        fleet_state = FLEET_STATE_PENDING
    elif lifecycle_state == FLEET_STATE_BILLING:
        fleet_state = FLEET_STATE_BILLING
    elif lifecycle_state == FLEET_STATE_TRIALING:
        fleet_state = FLEET_STATE_TRIALING
    elif lifecycle_state == FLEET_STATE_LIVE or lifecycle_state == "active":
        fleet_state = FLEET_STATE_LIVE
    else:
        fleet_state = lifecycle_state

    heatmap_tier = _FLEET_TO_HEATMAP.get(fleet_state, "warn")
    state_label = fleet_state.replace("_", " ").title()

    return {
        "fleet_state": fleet_state,
        "fleet_state_label": state_label,
        "heatmap_tier": heatmap_tier,
        "lifecycle": lifecycle,
        "lifecycle_state": lifecycle_state,
        "is_active": bool(getattr(school, "is_active", False)),
        "is_approved": bool(getattr(school, "is_approved", False)),
        "is_frozen": bool(getattr(school, "is_frozen", False)),
        "provisioning_in_flight": fleet_state == FLEET_STATE_PROVISIONING,
        "provision_error": fleet_state == FLEET_STATE_PROVISION_ERROR,
    }


def _school_display_label(school) -> str:
    name = (getattr(school, "name", None) or "").strip()
    if name:
        return name[:48]
    slug = (getattr(school, "slug", None) or "").strip()
    return slug[:48] if slug else "—"


def resolve_fleet_tile(school, *, cached_subscription=_SUBSCRIPTION_UNSET) -> dict[str, Any]:
    """Heatmap tile payload for one school."""
    status = resolve_school_fleet_status(school, cached_subscription=cached_subscription)
    slug = getattr(school, "slug", "") or ""
    return {
        "label": _school_display_label(school),
        "status": status["heatmap_tier"],
        "fleet_state": status["fleet_state"],
        "fleet_state_label": status["fleet_state_label"],
        "cell_value": status["fleet_state_label"],
        "cell_secondary": status["lifecycle_state"].replace("_", " ").title(),
        "tenant_slug": slug,
        "school_id": str(getattr(school, "pk", "") or ""),
        "tooltip": f"{_school_display_label(school)} · {status['fleet_state_label']}",
    }


def resolve_fleet_summary(schools=None) -> dict[str, Any]:
    """Aggregate fleet counts by heatmap tier and fleet_state."""
    if schools is None:
        schools = list(build_fleet_queryset())
    subs = batch_current_subscriptions(schools)

    tier_counts = {t: 0 for t in HEATMAP_TIERS}
    state_counts: dict[str, int] = {}
    total = 0

    for school in schools:
        total += 1
        row = resolve_school_fleet_status(school, cached_subscription=subs.get(school.pk))
        tier = row["heatmap_tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        fs = row["fleet_state"]
        state_counts[fs] = state_counts.get(fs, 0) + 1

    live_count = tier_counts.get("healthy", 0) + tier_counts.get("okay", 0)
    watch_count = tier_counts.get("warn", 0)
    critical_count = tier_counts.get("danger", 0)
    idle_count = tier_counts.get("idle", 0)

    return {
        "total": total,
        "live": live_count,
        "watch": watch_count,
        "critical": critical_count,
        "idle": idle_count,
        "tier_counts": tier_counts,
        "state_counts": state_counts,
        "healthy": tier_counts.get("healthy", 0),
        "okay": tier_counts.get("okay", 0),
        "warn": watch_count,
        "danger": critical_count,
    }


def resolve_fleet_tiles(*, max_tiles: int = 500) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """All fleet tiles (capped) + summary for heatmap / live JSON."""
    schools = list(build_fleet_queryset())
    subs = batch_current_subscriptions(schools)
    summary = resolve_fleet_summary(schools)

    tiles: list[dict[str, Any]] = []
    for school in schools[:max_tiles]:
        tiles.append(resolve_fleet_tile(school, cached_subscription=subs.get(school.pk)))

    return tiles, summary


def fleet_revision(tiles: list[dict], summary: dict[str, Any]) -> str:
    """Stable fingerprint for live-poll change detection."""
    payload = {
        "total": summary.get("total"),
        "tier": summary.get("tier_counts"),
        "states": summary.get("state_counts"),
        "tiles": [
            {"id": t.get("school_id"), "s": t.get("fleet_state"), "h": t.get("status")}
            for t in tiles
        ],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_fleet_summary_label(summary: dict[str, Any]) -> str:
    """Compact pulse sub-label, e.g. '2 live · 1 watch · 1 critical'."""
    parts: list[str] = []
    live = int(summary.get("live") or 0)
    watch = int(summary.get("watch") or 0)
    critical = int(summary.get("critical") or 0)
    idle = int(summary.get("idle") or 0)
    total = int(summary.get("total") or 0)
    if live:
        parts.append(_("{n} live").format(n=live))
    if watch:
        parts.append(_("{n} watch").format(n=watch))
    if critical:
        parts.append(_("{n} critical").format(n=critical))
    if idle:
        parts.append(_("{n} idle").format(n=idle))
    if not parts and total:
        parts.append(_("{n} total").format(n=total))
    return " · ".join(str(p) for p in parts) if parts else str(_("No schools"))


def format_heatmap_meta(*, shown: int, summary: dict[str, Any]) -> str:
    """Meta line under heatmap title."""
    total = int(summary.get("total") or shown)
    ts = timezone.now().strftime("%H:%M")
    breakdown = format_fleet_summary_label(summary)
    return str(
        _("{shown} of {total} · {breakdown} · refreshed {ts}").format(
            shown=shown,
            total=total,
            breakdown=breakdown,
            ts=ts,
        )
    )


def invalidate_fleet_status_cache() -> None:
    """Hook for signal handlers after school lifecycle mutations."""
    try:
        from django.core.cache import cache

        cache.delete(FLEET_STATUS_CACHE_KEY)
    except Exception:
        logger.warning("fleet_status: cache invalidate failed", exc_info=True)
