"""Unified operator fleet snapshot — globe, pulse, summary (platform-wide SOT)."""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

OPERATOR_FLEET_REVISION_KEY = "rmc:operator:fleet:revision:v1"
PULSE_CACHE_KEY = "rmc:operator:fleet:pulse:v1"
PULSE_CACHE_TTL = 15  # magic-number-allow: operator-fleet-pulse-cache-seconds

FLEET_PULSE_EVENT_TYPES: tuple[str, ...] = (
    "provisioning_started",
    "provisioning_completed",
    "signup_verified_tenant_active",
    "fleet_governed_change_created",
    "fleet_governed_change_transitioned",
    "blueprint_applied",
    "workflow_activated",
)

_EVENT_LABELS: dict[str, str] = {
    "provisioning_started": _("Provisioning started"),
    "provisioning_completed": _("School now live"),
    "signup_verified_tenant_active": _("Signup verified · tenant active"),
    "fleet_governed_change_created": _("Fleet change drafted"),
    "fleet_governed_change_transitioned": _("Fleet change updated"),
    "blueprint_applied": _("Blueprint applied"),
    "workflow_activated": _("Workflow pack activated"),
}


def bump_operator_fleet_revision() -> str:
    """Invalidate unified operator fleet revision (globe + bus + pulse)."""
    rev = hashlib.sha256(f"{time.time():.6f}".encode()).hexdigest()[:16]
    try:
        cache.set(OPERATOR_FLEET_REVISION_KEY, rev, timeout=604800)
        cache.delete(PULSE_CACHE_KEY)
        from apps.schools.fleet_status import invalidate_fleet_status_cache

        invalidate_fleet_status_cache()
    except Exception:
        logger.warning("operator_fleet: revision bump failed", exc_info=True)
    return rev


def get_operator_fleet_revision() -> str:
    cached = cache.get(OPERATOR_FLEET_REVISION_KEY)
    if cached:
        return str(cached)
    return bump_operator_fleet_revision()


def _relative_time_label(created_at) -> str:
    if not created_at:
        return ""
    now = timezone.now()
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at, dt_timezone.utc)
    delta = max(0, int((now - created_at).total_seconds()))
    if delta < 60:
        return str(_("now"))
    if delta < 3600:
        return str(_("{mins}m").format(mins=delta // 60))
    if delta < 86400:
        return str(_("{hrs}h").format(hrs=delta // 3600))
    return str(_("{days}d").format(days=delta // 86400))


def _pulse_line_for_event(event_type: str, payload: dict[str, Any]) -> str:
    base = _EVENT_LABELS.get(event_type, event_type.replace("_", " "))
    region_hint = (payload.get("region") or payload.get("country_code") or "").strip()
    if region_hint:
        return f"{base} · {region_hint}"
    slug_hash = payload.get("slug_hash") or ""
    if slug_hash:
        return f"{base} · #{slug_hash[:8]}"
    return str(base)


def fetch_fleet_pulse_events(*, limit: int = 3) -> list[dict[str, Any]]:
    """PII-safe pulse lines from PlatformEventLog (fleet-visible types only)."""
    cached = cache.get(PULSE_CACHE_KEY)
    if cached is not None:
        return cached

    out: list[dict[str, Any]] = []
    try:
        from apps.platform_runtime.models import PlatformEventLog

        qs = (
            PlatformEventLog.objects.filter(event_type__in=FLEET_PULSE_EVENT_TYPES)
            .order_by("-created_at")[: max(limit, 1)]
        )
        for row in qs:
            payload = row.payload if isinstance(row.payload, dict) else {}
            safe_payload = {
                k: v
                for k, v in payload.items()
                if k in {"region", "country_code", "slug_hash", "fleet_state", "status"}
            }
            if row.school_id and not safe_payload.get("slug_hash"):
                safe_payload["school_id_hash"] = hashlib.sha256(
                    str(row.school_id).encode()
                ).hexdigest()[:12]
            out.append(
                {
                    "event_type": row.event_type,
                    "text": _pulse_line_for_event(row.event_type, safe_payload),
                    "time_label": _relative_time_label(row.created_at),
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )
    except Exception:
        logger.warning("operator_fleet: pulse fetch failed", exc_info=True)

    try:
        cache.set(PULSE_CACHE_KEY, out, PULSE_CACHE_TTL)
    except Exception:
        pass
    return out


def _school_hours_regions_detail() -> tuple[int, list[str]]:
    """Regions where local hour is 08:00–15:00 (approximate from fleet markers)."""
    try:
        from apps.siteconfig.views_globe_api import _school_rows_for_globe
        from apps.siteconfig.world_map_geo import build_globe_markers

        rows = _school_rows_for_globe()
        markers = build_globe_markers(rows)
        regions: set[str] = set()
        now_utc = datetime.now(dt_timezone.utc)
        utc_hour = now_utc.hour
        for m in markers:
            region = m.get("region") or ""
            lng = float(m.get("lng") or 0)
            approx_local = (utc_hour + int(lng / 15)) % 24
            if 8 <= approx_local < 15 and region:
                regions.add(region)
        ordered = sorted(regions)
        return len(ordered), ordered
    except Exception:
        return 0, []


def _school_hours_regions_count() -> int:
    count, _ = _school_hours_regions_detail()
    return count


def rules_whisper_line(
    *,
    schools_live: int = 0,
    suspended: int = 0,
    frozen: int = 0,
    visible_count: int | None = None,
) -> str:
    if suspended or frozen:
        parts = []
        if suspended:
            parts.append(str(_("{n} suspended").format(n=suspended)))
        if frozen:
            parts.append(str(_("{n} frozen").format(n=frozen)))
        return str(_("Fleet attention · {detail}").format(detail=" · ".join(parts)))
    if schools_live <= 0:
        return str(_("No live schools on the map yet"))
    if visible_count is not None:
        return str(
            _("Fleet healthy · {n} visible in view").format(n=visible_count)
        )
    return str(_("Fleet healthy · {n} schools live").format(n=schools_live))


def rules_fleet_brief(
    *,
    schools_live: int = 0,
    suspended: int = 0,
    frozen: int = 0,
    summary_label: str = "",
    pulse_events: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    headline_parts = [str(_("{n} schools live").format(n=schools_live))]
    if suspended:
        headline_parts.append(str(_("{n} need eyes").format(n=suspended + frozen)))
    headline = ". ".join(headline_parts) + "."
    body_bits = []
    if summary_label:
        body_bits.append(summary_label)
    elif pulse_events:
        body_bits.append(pulse_events[0].get("text") or "")
    if suspended and not body_bits:
        body_bits.append(str(_("Review suspended tenants in the registry.")))
    body = " ".join(x for x in body_bits if x).strip()
    return {"headline": headline, "body": body or str(_("All clear on the fleet map."))}


def build_operator_fleet_snapshot(*, pulse_limit: int = 3) -> dict[str, Any]:
    """Merge fleet summary, globe revision, pulse, and rules-layer AI copy."""
    from apps.siteconfig.views_globe_api import _globe_query_bundle
    from apps.schools.fleet_live_payload import build_fleet_live_payload
    from django.http import HttpRequest

    try:
        fleet_payload = build_fleet_live_payload(include_rows=False)
    except Exception:
        logger.warning("operator_fleet: fleet payload fallback", exc_info=True)
        fleet_payload = {
            "summary": {"live": 0, "suspended": 0, "frozen": 0},
            "summary_label": "",
        }

    try:
        req = HttpRequest()
        req.GET = {}
        globe_data = _globe_query_bundle(req, include_operator=False)
    except Exception:
        logger.warning("operator_fleet: globe bundle fallback", exc_info=True)
        summary = fleet_payload.get("summary") or {}
        active_fb = int(summary.get("live") or 0)
        globe_data = {
            "revision": None,
            "schools_live": active_fb,
            "suspended": int(summary.get("suspended") or 0),
            "frozen": int(summary.get("frozen") or 0),
            "marker_count": int(summary.get("live") or 0),
        }

    pulse = fetch_fleet_pulse_events(limit=pulse_limit)
    active = int(globe_data.get("schools_live") or fleet_payload.get("summary", {}).get("live") or 0)
    suspended = int(globe_data.get("suspended") or 0)
    frozen = int(globe_data.get("frozen") or 0)
    summary = fleet_payload.get("summary") or {}
    summary_label = fleet_payload.get("summary_label") or ""

    whisper = rules_whisper_line(
        schools_live=active,
        suspended=suspended,
        frozen=frozen,
    )
    brief = rules_fleet_brief(
        schools_live=active,
        suspended=suspended,
        frozen=frozen,
        summary_label=summary_label,
        pulse_events=pulse,
    )

    aurora = "good"
    if frozen:
        aurora = "danger"
    elif suspended:
        aurora = "warn"

    return {
        "operator_fleet_revision": get_operator_fleet_revision(),
        "globe_revision": globe_data.get("revision"),
        "ts": timezone.now().isoformat(),
        "schools_live": active,
        "suspended": suspended,
        "frozen": frozen,
        "marker_count": globe_data.get("marker_count"),
        "fleet_summary": summary,
        "summary_label": summary_label,
        "pulse_events": pulse,
        "whisper_line": whisper,
        "fleet_brief": brief,
        "school_hours_regions": _school_hours_regions_count(),
        "school_hours_regions_list": _school_hours_regions_detail()[1],
        "aurora": aurora,
        "features": {
            "void_zones": True,
            "fleet_pulse": True,
            "ai_whisper": True,
            "ai_brief": True,
            "wow_enabled": True,
            "globe_presence": True,
            "magnetic_fly_to": True,
            "void_parallax": True,
            "celebration_bloom": True,
            "executive_snapshot": True,
            "day_arc": True,
            "context_lens": True,
            "pulse_timeline": True,
            "hero_metric": True,
            "glass_dock": True,
            "constellation_mode": True,
            "orbit_chips": True,
        },
        "regional_deltas": _regional_count_deltas(globe_data),
    }


def _regional_count_deltas(globe_data: dict[str, Any]) -> dict[str, int]:
    """Per-region +/− since last cached snapshot (Wow+ W16, PII-safe counts only)."""
    breakdown = globe_data.get("regional_breakdown") or []
    if not isinstance(breakdown, list):
        return {}
    current: dict[str, int] = {}
    for row in breakdown:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("region") or "").strip()
        if not label:
            continue
        try:
            current[label] = int(row.get("count") or 0)
        except (TypeError, ValueError):
            current[label] = 0
    cache_key = "rmc:operator:fleet:regional_counts:v1"
    prior = cache.get(cache_key) or {}
    deltas: dict[str, int] = {}
    for label, count in current.items():
        prev = prior.get(label)
        if prev is not None and int(prev) != count:
            deltas[label] = count - int(prev)
    try:
        cache.set(cache_key, current, timeout=604800)
    except Exception:
        pass
    return deltas
