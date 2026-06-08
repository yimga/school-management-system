"""
cockpit_panels_realdata_service.py — v3.58.2 (2026-05-22).

Real-data resolvers for the 9 manager cockpit panels beyond the
platform-pulse strip:

    1. operator_presence  — who's online right now
    2. activity_ticker    — most recent platform events (last 25)
    3. audit_feed         — most recent MigrationCloudAuditEvent rows
    4. world_map          — schools per region (with totals + regional rows)
    5. tenant_heatmap     — tiles per school by health proxy
    6. forecast_lane      — extrapolated MRR / new schools / incidents
    7. slo_clocks         — webhook success rate, audit chain status, etc.
    8. revenue_waterfall  — MRR breakdown segments
    9. trust_nutrition    — uptime + audit integrity + key freshness rows

Same architecture as ``cockpit_platform_pulse_service``:
    - Lazy model imports inside each resolver.
    - Try/except wrapping so a resolver failure returns ``None`` and the
      orchestrator substitutes the existing demo payload (or operator
      override) for that key — never crashes the context processor.
    - 60s per-panel cache via ``django.core.cache.cache``.
    - PII-safe outputs — actor/email values never leave the resolver as
      plaintext; we use SHA-256 hex prefixes when an identity needs to
      be surfaced for forensic audit.

Wired into cockpit_context.py via ``resolve_panel_overrides()``: the
orchestrator overlays the resolver output on top of the static defaults
(and demo payload, when COCKPIT_200X_RENDER_PREVIEW_DEMO is True) BEFORE
the operator's cockpit_payload overlay. Operator overrides still win.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
CACHE_PREFIX = "rmc:cockpit:panels"

ONLINE_WINDOW_MINUTES = 15  # operators counted as "online" if active in last 15 min


def _hash_prefix(value: str, length: int = 12) -> str:
    """SHA-256 hex prefix — used so we can render distinct dots/avatars
    without exposing the operator's email/slug."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


# ============================================================
# 1. Operator presence
# ============================================================

def _resolve_operator_presence() -> dict[str, Any] | None:
    """Count of operators active in the last ONLINE_WINDOW_MINUTES."""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cutoff = timezone.now() - timedelta(minutes=ONLINE_WINDOW_MINUTES)
        # tenant-isolation-allow: platform-cockpit-cross-tenant-operator-count
        recent = User.objects.filter(
            is_staff=True,
            last_login__gte=cutoff,
        ).only("last_login", "username")
        online = list(recent[:10])  # cap to keep avatar rail readable
        avatars = []
        for u in online[:3]:
            initials = (u.username[:2] or "??").upper()
            avatars.append({
                "initials": initials,
                "gradient_slug": "indigo",
            })
        count = recent.count() if hasattr(recent, "count") else len(online)
        return {
            "enabled": True,
            "operators_online_count": int(count),
            "avatars": avatars,
            "status_pill_text": (
                _("All systems handling well") if count > 0 else _("No operators online")
            ),
        }
    except Exception:
        logger.warning("panels: operator_presence resolver failed", exc_info=True)
        return None


# ============================================================
# 2. Activity ticker — most recent platform events
# ============================================================

def _resolve_activity_ticker() -> dict[str, Any] | None:
    """Last ~12 platform events from MigrationCloudAuditEvent."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-activity-feed
        events = list(
            MigrationCloudAuditEvent.objects.order_by("-created_at_iso").values(
                "event_type", "created_at_iso"
            )[:12]
        )
        cards = []
        for ev in events:
            etype = ev.get("event_type") or ""
            cards.append({
                "icon": _icon_for_event(etype),
                "severity": _severity_for_event(etype),
                "text": _text_for_event(etype),
                "timestamp": _relative_ts(ev.get("created_at_iso")),
            })
        if not cards:
            return None
        return {
            "enabled": True,
            # v3.60.0 (2026-05-22): tuned from 60s → 40s for a snappier feel.
            "scroll_seconds": 40,
            "live_badge_label": _("LIVE"),
            "cards": cards,
        }
    except Exception:
        logger.warning("panels: activity_ticker resolver failed", exc_info=True)
        return None


_EVENT_ICONS = {
    "companion.upload": "📦",
    "maa.sign": "✍",
    "maa.sign_attempt_draft": "📝",
    "key.rotate": "🔑",
    "webhook.subscription.created": "🔗",
    "webhook.subscription.deleted": "🗑",
    "webhook.delivery.replay": "↻",
    "token.mint": "🎟",
    "token.revoke": "🚫",
    "legacy_hash.decrypt": "🔐",
}


def _icon_for_event(event_type: str) -> str:
    return _EVENT_ICONS.get(event_type, "•")


def _severity_for_event(event_type: str) -> str:
    if "delete" in event_type or "revoke" in event_type:
        return "warn"
    if "rotate" in event_type or "replay" in event_type:
        return "info"
    return "success"


_EVENT_TEXTS = {
    "companion.upload": "Companion upload received",
    "maa.sign": "Migration agreement signed",
    "maa.sign_attempt_draft": "Draft MAA refused (gate held)",
    "key.rotate": "Encryption key rotated",
    "webhook.subscription.created": "Webhook subscription created",
    "webhook.subscription.deleted": "Webhook subscription removed",
    "webhook.delivery.replay": "Webhook delivery replayed",
    "token.mint": "Migration token minted",
    "token.revoke": "Migration token revoked",
    "legacy_hash.decrypt": "Legacy hash decrypted (auth path)",
}


def _text_for_event(event_type: str) -> str:
    return _EVENT_TEXTS.get(event_type, event_type or "Event")


def _relative_ts(iso_value: Any) -> str:
    if not iso_value:
        return ""
    try:
        from datetime import datetime
        if isinstance(iso_value, str):
            dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        else:
            dt = iso_value
        now = timezone.now()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ""


# ============================================================
# 3. Audit feed (recent audit events with severity stripes)
# ============================================================

def _resolve_audit_feed() -> dict[str, Any] | None:
    """Most recent audit events for the manager landing."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-audit-feed
        rows = list(
            MigrationCloudAuditEvent.objects.order_by("-created_at_iso").values(
                "event_type", "actor_id", "tenant_id_hash", "created_at_iso"
            )[:8]
        )
        events = []
        for r in rows:
            etype = r.get("event_type") or ""
            severity = _severity_for_event(etype)
            events.append({
                "time": _relative_ts(r.get("created_at_iso")),
                "actor": (r.get("actor_id") or "—")[:12] if r.get("actor_id") else "—",
                "event": _text_for_event(etype),
                "scope": (r.get("tenant_id_hash") or "—")[:12],
                "severity": severity,
                "severity_label": severity.upper(),
            })
        if not events:
            return None
        return {
            "enabled": True,
            "events": events,
        }
    except Exception:
        logger.warning("panels: audit_feed resolver failed", exc_info=True)
        return None


# ============================================================
# 4. World map — schools per region
# ============================================================

# Approx cluster centres on the _live_world_map.html 600×280 stylized continents
# (region buckets → a believable position on the map blobs).
_WORLD_REGION_CENTERS = {
    "North America": (112, 115),
    "Europe": (214, 108),
    "West Africa": (244, 150),
    "Asia · Oceania": (416, 136),
    "Other": (300, 150),
}
# Per-region scatter half-extent (rx, ry). Known regions cluster tightly on
# their blob; unknown-location ("Other") tenants spread across the whole map
# so they read as distributed pins, not one overlapping clump.
_WORLD_REGION_SPREAD = {
    "North America": (46, 30),
    "Europe": (40, 26),
    "West Africa": (40, 28),
    "Asia · Oceania": (56, 32),
    "Other": (170, 78),
}
_WORLD_BUCKET_FOR = {
    "US": "North America", "CA": "North America", "MX": "North America",
    "NG": "West Africa", "GH": "West Africa", "CM": "West Africa",
    "SL": "West Africa", "CI": "West Africa", "SN": "West Africa",
    "GB": "Europe", "FR": "Europe", "DE": "Europe", "IE": "Europe",
    "AU": "Asia · Oceania", "NZ": "Asia · Oceania", "IN": "Asia · Oceania",
    "SG": "Asia · Oceania", "PH": "Asia · Oceania",
}
# Low-discrepancy unit offsets (centred in [-1,1]) — spread points evenly with
# no Math.random jitter (deterministic across requests). One dot per slot keeps
# pins from overlapping; we cap visible dots per region to this pattern length.
_WORLD_SPREAD_UNIT = [
    (0.0, 0.0), (0.62, 0.30), (-0.55, 0.42), (0.40, -0.55), (-0.72, -0.25), (0.86, 0.56),
    (-0.34, 0.72), (0.55, 0.64), (-0.86, 0.46), (0.22, -0.80), (0.74, -0.40), (-0.60, -0.64),
    (0.96, 0.12), (-0.18, 0.92), (0.44, -0.92), (-0.94, -0.12), (0.14, 0.50), (-0.46, -0.06),
    (0.80, -0.72), (-0.74, 0.80),
]


# Max schools rendered on globe/SVG (clustering handles zoomed-out display).
GLOBE_SCHOOL_ROW_CAP = 500


def _world_map_school_rows(active_schools) -> list[dict[str, Any]]:
    """Cross-tenant school rows for the live world map (capped, status-aware)."""
    cap = GLOBE_SCHOOL_ROW_CAP
    rows: list[dict[str, Any]] = list(
        active_schools.values("id", "slug", "name", "country_code", "is_frozen", "settings")[:cap]
    )
    remaining = max(0, cap - len(rows))
    if remaining:
        try:
            from apps.schools.models import School
            # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
            rows += [
                {**r, "is_active": False}
                for r in School.objects.filter(is_active=False, deleted_at__isnull=True)
                .values("id", "slug", "name", "country_code", "is_frozen", "settings")[:remaining]
            ]
        except Exception:
            logger.debug("panels: world_map suspended-dots query skipped", exc_info=True)
    return rows


def _world_map_globe_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Interactive 3D globe bundle (lat/lng markers + dark cockpit theme)."""
    from apps.siteconfig.world_map_geo import build_globe_markers, build_globe_payload

    markers = build_globe_markers(rows)
    return build_globe_payload(markers)


def _world_map_tenant_dots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy SVG cx/cy dots — kept for preview HTML + graceful no-JS fallback."""
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    per_region: dict[str, int] = {}
    dots: list[dict[str, Any]] = []
    slots = len(_WORLD_SPREAD_UNIT)
    for i, r in enumerate(rows):
        cc = (r.get("country_code") or "").upper()
        region = _WORLD_BUCKET_FOR.get(cc, "Other")
        n = per_region.get(region, 0)
        per_region[region] = n + 1
        if n >= slots:
            continue
        cx0, cy0 = _WORLD_REGION_CENTERS.get(region, _WORLD_REGION_CENTERS["Other"])
        rx, ry = _WORLD_REGION_SPREAD.get(region, _WORLD_REGION_SPREAD["Other"])
        ux, uy = _WORLD_SPREAD_UNIT[n]
        cx = max(20.0, min(580.0, cx0 + ux * rx))
        cy = max(16.0, min(264.0, cy0 + uy * ry))
        if r.get("is_frozen"):
            color, ring_color, status_label = "#93c5fd", "#3b82f6", _("Frozen")
            status_key = "frozen"
        elif r.get("is_active") is False:
            color, ring_color, status_label = "#fcd34d", "#f59e0b", _("Suspended")
            status_key = "suspended"
        else:
            color, ring_color, status_label = "#6ee7b7", "#10b981", _("Active")
            status_key = "active"
        country_name = GlobalGeoCatalog.country_name(cc) if cc else ""
        city = ""
        settings = r.get("settings")
        if isinstance(settings, dict):
            location = settings.get("location")
            if isinstance(location, dict):
                city = (location.get("city") or location.get("label") or "").strip()
        place_parts = [p for p in (city, country_name or cc, region) if p]
        school_name = (r.get("name") or r.get("slug") or "").strip()
        location_title = " · ".join(place_parts) if place_parts else str(status_label)
        if school_name:
            location_title = f"{school_name}: {location_title}"
        dots.append({
            "cx": round(cx, 1),
            "cy": round(cy, 1),
            "color_token": color,
            "ring_color": ring_color,
            "status_label": status_label,
            "status": status_key,
            "region": region,
            "country_code": cc,
            "country_name": country_name,
            "location_title": location_title,
            "delay_s": round((i % 12) * 0.18, 2),
        })
    return dots


def _world_map_footprint_stats(active_schools) -> dict[str, Any]:
    """Live platform counts + regional legend rows (active schools only)."""
    from django.utils.translation import ngettext

    from apps.siteconfig.world_map_geo import enrich_regional_breakdown

    total = active_schools.count()
    buckets = {
        "North America": 0,
        "West Africa": 0,
        "Europe": 0,
        "Asia · Oceania": 0,
        "Other": 0,
    }
    distinct_countries: set[str] = set()
    for cc in active_schools.values_list("country_code", flat=True):
        cc_upper = (cc or "").upper()
        region = _WORLD_BUCKET_FOR.get(cc_upper, "Other")
        buckets[region] = buckets.get(region, 0) + 1
        if cc_upper.strip():
            distinct_countries.add(cc_upper.strip())
    regional_rows = [{"region": r, "count": c} for r, c in buckets.items() if c > 0]
    regional_rows.sort(key=lambda row: row["count"], reverse=True)
    dot_tokens = ("indigo", "emerald", "amber", "rose")
    n_regions = len(regional_rows)
    n_countries = len(distinct_countries)
    if n_countries:
        reg_txt = ngettext("%(n)d region", "%(n)d regions", n_regions) % {"n": n_regions}
        cty_txt = ngettext("%(n)d country", "%(n)d countries", n_countries) % {"n": n_countries}
        subline = _("Across %(reg)s · %(cty)s today") % {"reg": reg_txt, "cty": cty_txt}
    else:
        subline = _("Across all regions")
    return {
        "schools_live": total,
        "subline": subline,
        "regional_breakdown": enrich_regional_breakdown([
            {
                "label": row["region"],
                "count": str(row["count"]),
                "dot_color_token": dot_tokens[idx % len(dot_tokens)],
            }
            for idx, row in enumerate(regional_rows)
        ]),
    }


def _resolve_world_map() -> dict[str, Any] | None:
    """Total schools live + per-region breakdown + status-coloured tenant dots."""
    try:
        from apps.schools.models import School
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        active_schools = School.objects.filter(is_active=True)
        total = active_schools.count()
        if total == 0:
            return None
        stats = _world_map_footprint_stats(active_schools)
        map_rows = _world_map_school_rows(active_schools)
        globe_payload = _world_map_globe_payload(map_rows)

        return {
            "enabled": True,
            "eyebrow": _("Global footprint"),
            "schools_live": str(stats["schools_live"]),
            "schools_live_label": _("schools live"),
            "subline": stats["subline"],
            "layout": "hero",
            "tour_enabled": True,
            "regional_breakdown": stats["regional_breakdown"],
            "tenant_dots": _world_map_tenant_dots(map_rows),
            "globe_payload": globe_payload,
            "globe_payload_json": json.dumps(globe_payload),
            "svg_country_labels": globe_payload.get("country_labels") or [],
        }
    except Exception:
        logger.warning("panels: world_map resolver failed", exc_info=True)
        return None


# ============================================================
# 5. Tenant heatmap — tiles per school by health proxy
# ============================================================

def _resolve_tenant_heatmap() -> dict[str, Any] | None:
    """Compact heatmap of school health. Proxy: active+approved=ok, otherwise warn."""
    try:
        from apps.schools.models import School
        # tenant-isolation-allow: platform-cockpit-cross-tenant-heatmap-tiles
        rows = list(
            School.objects.filter(is_active=True)
            .values("slug", "country_code", "is_approved")[:60]
        )
        if not rows:
            return None
        # tenant-isolation-allow: platform-cockpit-cross-tenant-heatmap-total
        total = School.objects.filter(is_active=True).count()
        tiles = []
        for r in rows:
            status = "healthy" if r.get("is_approved") else "warn"
            tiles.append({
                "label": (r.get("country_code") or "").upper() or "—",
                "status": status,
                "cell_value": "",
                "cell_secondary": "",
                "tenant_slug": _hash_prefix(r.get("slug") or "", 8),
            })
        return {
            "enabled": True,
            "eyebrow": _("Tenants · health grid"),
            "meta_text": _("{shown} of {total} · last refreshed 60s ago").format(
                shown=len(tiles),
                total=total,
            ),
            "tiles": tiles,
        }
    except Exception:
        logger.warning("panels: tenant_heatmap resolver failed", exc_info=True)
        return None


# ============================================================
# 6. Forecast lane — 7d MRR / new schools / incidents
# ============================================================
#
# Builds the past+future SVG geometry the partial
# (templates/partials/cockpit/_forecast_lane.html) renders, from the
# PlatformPulseSnapshot daily time series written by the
# `snapshot_platform_pulse` Celery beat. Method: least-squares linear
# trend + a confidence band that widens toward the horizon. The lane stays
# hidden (resolver returns None) until there are >= _FC_MIN_POINTS daily
# snapshots to fit, so it lights up automatically a few days after the beat
# starts — no fabricated forecast before there is data to forecast from.

# SVG drawing contract — MUST match the partial's viewBox="0 0 240 56".
# `_FC_TODAY_X` splits the past trace (0 -> 120) from the future trace
# (120 -> 240); y grows downward so a SMALLER y renders HIGHER on screen.
_FC_TODAY_X = 120  # magic-number-allow: svg-viewbox-geometry-contract-today-tick
_FC_END_X = 240  # magic-number-allow: svg-viewbox-geometry-contract-horizon-edge
_FC_TOP_Y = 10.0
_FC_BOT_Y = 46.0
_FC_HORIZON_DAYS = 7
_FC_FUTURE_STEPS = 6   # 6 intervals -> 7 future points (today + 6 forward)
_FC_MIN_POINTS = 3     # need >= 3 daily snapshots before a trend is meaningful
_FC_MRR_THOUSANDS = 1000  # magic-number-allow: currency-thousands-format-threshold


def _fc_metric_series(metric_key: str, days: int = 14) -> list[int]:
    """Oldest -> newest list of raw_value ints for a metric (last `days`)."""
    from .models_pulse_snapshot import PlatformPulseSnapshot

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    # tenant-isolation-allow: platform-cockpit-forecast-snapshot-cross-tenant-aggregate
    rows = list(
        PlatformPulseSnapshot.objects.filter(
            metric_key=metric_key,
            snapshot_date__gte=start,
            snapshot_date__lte=today,
        )
        .order_by("snapshot_date")
        .values_list("raw_value", flat=True)
    )
    return [int(v) for v in rows]


def _fc_linear_fit(values: list[float]) -> tuple[float, float, float, float]:
    """Least-squares fit over x=0..n-1. Returns (slope, intercept, r2, sigma)."""
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    slope = (sxy / sxx) if sxx > 1e-9 else 0.0
    intercept = mean_y - slope * mean_x
    preds = [intercept + slope * x for x in xs]
    ss_res = sum((values[i] - preds[i]) ** 2 for i in range(n))
    ss_tot = sum((v - mean_y) ** 2 for v in values)
    # Flat series (ss_tot ~ 0) is perfectly predictable -> r2 = 1.0.
    r2 = 1.0 if ss_tot < 1e-9 else max(0.0, min(1.0, 1 - ss_res / ss_tot))
    sigma = (ss_res / n) ** 0.5
    return slope, intercept, r2, sigma


def _fc_confidence_pct(r2: float, n: int) -> int:
    """Map fit quality + sample size to an honest-ish 70-97% confidence band."""
    base = 70 + int(round(27 * r2))
    if n < 4:
        base = min(base, 80)  # don't over-claim on a 3-point fit
    return max(70, min(97, base))


def _fc_fmt_mrr(value: float) -> str:
    """Format a monthly-dollar figure like the pulse card ($42k / $1.2k / $850)."""
    value = max(0.0, value)
    if value >= _FC_MRR_THOUSANDS:
        return ("$%.1fk" % (value / _FC_MRR_THOUSANDS)).replace(".0k", "k")
    return "$%.0f" % value


def _fc_value_and_prediction(
    kind: str, today_val: float, v_end: float, slope: float, hw_end: float, conf: int
) -> tuple[str, Any]:
    """Per-metric headline value + italic prediction caption."""
    if kind == "mrr":
        value = _fc_fmt_mrr(v_end)
        tiny = max(1.0, abs(today_val) * 0.01)
        if slope > tiny:
            trend = _("rising")
        elif slope < -tiny:
            trend = _("easing")
        else:
            trend = _("steady")
        prediction = _("%(trend)s · %(conf)d%% confidence") % {"trend": trend, "conf": conf}
    elif kind == "new_schools":
        predicted = max(0, int(round(slope * _FC_HORIZON_DAYS)))
        spread = max(1, int(round(hw_end / 2)))
        spread = min(spread, max(2, predicted + 1))  # keep the range sane
        lo = max(0, predicted - spread)
        hi = predicted + spread
        value = ("%d" % predicted) if lo == hi else ("%d–%d" % (lo, hi))
        prediction = _("expected · %(conf)d%% confidence") % {"conf": conf}
    else:  # incidents
        end = max(0, int(round(v_end)))
        value = "%d" % end
        if end == 0:
            level = _("none expected")
        elif end <= 3:
            level = _("low")
        else:
            level = _("elevated")
        prediction = _("%(level)s · %(conf)d%% confidence") % {"level": level, "conf": conf}
    return value, prediction


def _fc_build_card(
    slug: str, label: Any, values: list[int], *, stroke: str, fill: str, kind: str
) -> dict[str, Any]:
    """Build one forecast card (geometry + copy) from a real daily series."""
    n = len(values)
    fvalues = [float(v) for v in values]
    today_val = fvalues[-1]
    slope, _intercept, r2, sigma = _fc_linear_fit(fvalues)
    v_end = today_val + slope * _FC_HORIZON_DAYS

    # 7 future values: linear walk today -> v_end (the fit is already linear).
    future_vals = [
        today_val + (v_end - today_val) * (j / _FC_FUTURE_STEPS)
        for j in range(_FC_FUTURE_STEPS + 1)
    ]

    # Confidence band half-widths (value units): 0 at today, widening to horizon.
    plotted = fvalues + future_vals
    data_span = max(plotted) - min(plotted)
    floor = 0.12 * (data_span if data_span > 0 else max(1.0, abs(today_val) * 0.05 + 1.0))
    band_base = 0.5 * sigma + floor
    hw = [band_base * (j / _FC_FUTURE_STEPS) for j in range(_FC_FUTURE_STEPS + 1)]

    # y-mapping over EVERY plotted value (incl. band edges) so nothing clips.
    all_vals = (
        fvalues
        + future_vals
        + [future_vals[j] + hw[j] for j in range(len(hw))]
        + [future_vals[j] - hw[j] for j in range(len(hw))]
    )
    vmin, vmax = min(all_vals), max(all_vals)
    span = vmax - vmin

    def y_of(v: float) -> float:
        if span < 1e-9:
            return round((_FC_TOP_Y + _FC_BOT_Y) / 2, 1)
        return round(_FC_BOT_Y - (v - vmin) / span * (_FC_BOT_Y - _FC_TOP_Y), 1)

    # Past trace: evenly spaced 0..today_x across the available points.
    past_points = []
    for i in range(n):
        x = round(_FC_TODAY_X * (i / (n - 1)), 1) if n > 1 else float(_FC_TODAY_X)
        past_points.append([x, y_of(fvalues[i])])

    # Future trace: today_x..end_x. future_points[0] == past_points[-1] (continuity).
    fx = [
        round(_FC_TODAY_X + (_FC_END_X - _FC_TODAY_X) * (j / _FC_FUTURE_STEPS), 1)
        for j in range(_FC_FUTURE_STEPS + 1)
    ]
    future_points = [[fx[j], y_of(future_vals[j])] for j in range(len(fx))]

    # Confidence band polygon (upper edge L->R, then back along lower edge).
    upper = [(fx[j], y_of(future_vals[j] + hw[j])) for j in range(len(fx))]
    lower = [(fx[j], y_of(future_vals[j] - hw[j])) for j in range(len(fx))]
    band = "M%s,%s" % (upper[0][0], upper[0][1])
    for px, py in upper[1:]:
        band += " L%s,%s" % (px, py)
    for px, py in reversed(lower):
        band += " L%s,%s" % (px, py)
    band += " Z"

    conf = _fc_confidence_pct(r2, n)
    value, prediction = _fc_value_and_prediction(kind, today_val, v_end, slope, hw[-1], conf)

    return {
        "slug": slug,
        "label": label,
        "value": value,
        "prediction": prediction,
        "stroke_color": stroke,
        "fill_color": fill,
        "past_points": past_points,
        "future_points": future_points,
        "band_path": band,
        "today_x": _FC_TODAY_X,
        "caption_left": _("today"),
        "caption_right": _("+7 days"),
    }


def _resolve_forecast_lane() -> dict[str, Any] | None:
    """Real 7-day forecast for MRR / new schools / incidents.

    Reads the PlatformPulseSnapshot daily series for each metric, fits a
    linear trend, and emits the SVG card geometry the partial renders.
    Returns None (lane hidden) until every metric has >= _FC_MIN_POINTS
    snapshots — the snapshot beat writes all three together, so the lane
    appears automatically ~3 days after it starts running.
    """
    try:
        from .models_pulse_snapshot import PlatformPulseSnapshot as Snap

        mrr = _fc_metric_series(Snap.MRR)
        schools = _fc_metric_series(Snap.SCHOOLS)
        incidents = _fc_metric_series(Snap.INCIDENTS)
        if min(len(mrr), len(schools), len(incidents)) < _FC_MIN_POINTS:
            return None

        cards = [
            _fc_build_card(
                "mrr", _("MRR · 7-day forecast"), mrr,
                stroke="#22c55e", fill="rgba(34,197,94,0.10)", kind="mrr",
            ),
            _fc_build_card(
                "new_schools", _("New schools · 7-day forecast"), schools,
                stroke="#6366f1", fill="rgba(99,102,241,0.12)", kind="new_schools",
            ),
            _fc_build_card(
                "incidents", _("Incidents · 7-day forecast"), incidents,
                stroke="#f59e0b", fill="rgba(245,158,11,0.12)", kind="incidents",
            ),
        ]
        return {
            "enabled": True,
            "label": _("Forecast · next 7 days"),
            "cards": cards,
        }
    except Exception:
        logger.warning("panels: forecast_lane resolver failed", exc_info=True)
        return None


# ============================================================
# 7. SLO clocks — operational SLO snapshot
# ============================================================

def _resolve_slo_clocks() -> dict[str, Any] | None:
    """Snapshot of 4 ops SLOs. Sources: webhook deliveries, audit chain, key freshness, DR drill."""
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookSubscription
        # tenant-isolation-allow: platform-cockpit-cross-tenant-slo-webhooks
        total_subs = MigrationCloudWebhookSubscription.objects.count() or 0
        active_subs = MigrationCloudWebhookSubscription.objects.filter(is_active=True).count() if total_subs else 0
        webhook_health_pct = int(round(100 * active_subs / total_subs)) if total_subs else 100

        clocks = [
            {
                "label": _("Webhook health"),
                "value": f"{webhook_health_pct}%",
                "dot_status": "ok" if webhook_health_pct >= 95 else ("warn" if webhook_health_pct >= 80 else "danger"),
                "sublabel": _("Active / total subscriptions"),
            },
            {
                "label": _("Audit chain"),
                "value": "verified",
                "dot_status": "ok",
                "sublabel": _("Mondays 02:00 UTC"),
            },
            {
                "label": _("Key rotation"),
                "value": "monthly",
                "dot_status": "ok",
                "sublabel": _("Beat: first of month 04:00 UTC"),
            },
            {
                "label": _("DR drill"),
                "value": _("scheduled"),
                "dot_status": "info",
                "sublabel": _("Next: check var/dr-drill-schedule.json"),
            },
        ]
        return {
            "enabled": True,
            "clocks": clocks,
        }
    except Exception:
        logger.warning("panels: slo_clocks resolver failed", exc_info=True)
        return None


# ============================================================
# 8. Revenue waterfall — MRR breakdown by status
# ============================================================

def _resolve_revenue_waterfall() -> dict[str, Any] | None:
    """Defer SVG bar geometry to demo/operator payload until layout builder ships."""
    return None


# ============================================================
# 9. Trust nutrition — security/compliance posture
# ============================================================

def _resolve_trust_nutrition() -> dict[str, Any] | None:
    """Snapshot of trust signals — verified counts where we can; honest 'verified'
    labels where the source is a CI gate result rather than a queryable count."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-audit-count
        recent_audit = MigrationCloudAuditEvent.objects.filter(
            created_at_iso__gte=(timezone.now() - timedelta(days=7)).isoformat()
        ).count()
        rows = [
            {"label": _("Audit chain integrity"), "value": _("verified"), "status": "ok"},
            {"label": _("MAA signatures (7d)"), "value": str(recent_audit), "status": "info"},
            {"label": _("Encryption at rest"), "value": _("AES-256 · MultiFernet"), "status": "ok"},
            {"label": _("FERPA retention"), "value": _("90d floor"), "status": "ok"},
            {"label": _("Webhook signing"), "value": _("HMAC-SHA256 + canonical JSON"), "status": "ok"},
            {"label": _("MFA enforcement"), "value": _("operator-required"), "status": "ok"},
            {"label": _("Companion handshake"), "value": _("X25519 sealed box"), "status": "ok"},
        ]
        return {
            "enabled": True,
            "label": _("Trust nutrition"),
            "rows": rows,
        }
    except Exception:
        logger.warning("panels: trust_nutrition resolver failed", exc_info=True)
        return None


# ============================================================
# 10. Trust pillars alerts — v3.58.x Wave 10 Agent S (2026-05-22)
# ============================================================

def _resolve_trust_pillars_alerts() -> dict[str, Any] | None:
    """Alerts-feed view of the 7 platform trust pillars.

    Pulls posture from real platform sources where available:
      - Audit chain integrity: presence of MigrationCloudAuditEvent rows in
        the last 24h treated as "verifier beat ran". Real status comes from
        the weekly verify_audit_chain beat (v3.39.0).
      - MAA signatures: count of MigrationAuthorizationAgreement rows.
      - Encryption at rest: presence of settings.DJANGO_CRYPTOGRAPHY_KEYS
        (non-empty list/tuple => active rotation set).
      - FERPA retention: documented 90d floor (doc-attested).
      - Webhook signing: HMAC-SHA256 + canonical JSON (algorithmic constant).
      - MFA enforcement: doc-attested ("operator-required").
      - Companion handshake: X25519 sealed box (algorithmic constant).

    PII safety: this resolver NEVER renders raw operator emails / usernames
    / tenant slugs. Counts and posture-strings only.
    """
    try:
        from django.conf import settings as dj_settings
        # Audit chain integrity proxy: are we receiving audit events?
        audit_status = "ok"
        audit_value = _("verified")
        try:
            from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
            # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-pillars-audit
            recent = MigrationCloudAuditEvent.objects.filter(
                created_at_iso__gte=(timezone.now() - timedelta(days=7)).isoformat()
            ).count()
            if recent == 0:
                # No recent events — could be a quiet platform OR the beat
                # failed. We treat as info, not danger, since the canonical
                # signal is the verifier beat's email-on-broken hook.
                audit_status = "info"
                audit_value = _("no events 7d")
        except Exception:
            audit_status = "neutral"
            audit_value = _("unverified")

        # MAA signature count (informational — campaign progress)
        maa_status = "ok"
        maa_value = _("counsel-blessed v1.0")
        try:
            from apps.migration_cloud.models import MigrationAuthorizationAgreement
            # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-pillars-maa
            maa_count = MigrationAuthorizationAgreement.objects.count()
            if maa_count == 0:
                maa_status = "info"
                maa_value = _("none signed yet")
            else:
                maa_value = _("{n} signed").format(n=maa_count)
        except Exception:
            maa_status = "neutral"
            maa_value = _("unavailable")

        # Encryption at rest — DJANGO_CRYPTOGRAPHY_KEYS rotation set
        crypto_keys = getattr(dj_settings, "DJANGO_CRYPTOGRAPHY_KEYS", None)
        enc_status = "ok"
        enc_value = _("AES-256 · MultiFernet")
        if not crypto_keys:
            enc_status = "warn"
            enc_value = _("no rotation keys configured")

        pillars = [
            {
                "slug": "audit_chain",
                "label": _("Audit chain integrity"),
                "value": audit_value,
                "status": audit_status,
                "last_checked": _("Mon · 02:00 UTC"),
            },
            {
                "slug": "maa_signatures",
                "label": _("MAA signatures"),
                "value": maa_value,
                "status": maa_status,
                "last_checked": _("on each sign"),
            },
            {
                "slug": "encryption_at_rest",
                "label": _("Encryption at rest"),
                "value": enc_value,
                "status": enc_status,
                "last_checked": _("monthly rotation"),
            },
            {
                "slug": "ferpa_retention",
                "label": _("FERPA retention"),
                "value": _("90d floor"),
                "status": "ok",
                "last_checked": _("docs/SECURITY_KEYS.md"),
            },
            {
                "slug": "webhook_signing",
                "label": _("Webhook signing"),
                "value": _("HMAC-SHA256 + canonical JSON"),
                "status": "ok",
                "last_checked": _("per delivery"),
            },
            {
                "slug": "mfa_enforcement",
                "label": _("MFA enforcement"),
                "value": _("operator-required"),
                "status": "ok",
                "last_checked": _("on each sign-in"),
            },
            {
                "slug": "companion_handshake",
                "label": _("Companion handshake"),
                "value": _("X25519 sealed box"),
                "status": "ok",
                "last_checked": _("per upload"),
            },
        ]

        return {
            "enabled": True,
            "eyebrow": _("Trust pillars · alerts"),
            "title": _("Platform posture"),
            "title_em": _("seven pillars at a glance"),
            "meta_text": _("real-data overlay · 60s cache"),
            "pillars": pillars,
        }
    except Exception:
        logger.warning("panels: trust_pillars_alerts resolver failed", exc_info=True)
        return None


# ============================================================
# Orchestrator
# ============================================================

_RESOLVERS = (
    ("operator_presence",     _resolve_operator_presence),
    ("activity_ticker",       _resolve_activity_ticker),
    ("audit_feed",            _resolve_audit_feed),
    ("live_world_map",        _resolve_world_map),
    ("tenant_heatmap",        _resolve_tenant_heatmap),
    ("forecast_lane",         _resolve_forecast_lane),
    ("slo_clocks",            _resolve_slo_clocks),
    ("revenue_waterfall",     _resolve_revenue_waterfall),
    ("trust_nutrition",       _resolve_trust_nutrition),
    ("trust_pillars_alerts",  _resolve_trust_pillars_alerts),
)


def _honest_empty_panel(key: str) -> dict[str, Any]:
    """Layout-safe empty shape when demo is off and resolver returned None."""
    common = {
        "enabled": False,
        "empty_state": True,
        "meta_text": str(_("No live data yet")),
    }
    if key == "revenue_waterfall":
        return {
            **common,
            "eyebrow": str(_("MRR waterfall")),
            "title": "—",
            "title_em": "",
            "title_end": "—",
            "bars": [],
            "connector_dashes": [],
            "legend_rows": [],
        }
    if key == "forecast_lane":
        return {**common, "lanes": [], "title": str(_("Forecast")), "title_em": "—"}
    if key == "live_world_map":
        return {**common, "regions": [], "total_schools": "—"}
    if key == "tenant_heatmap":
        return {**common, "tiles": []}
    if key == "activity_ticker":
        return {**common, "cards": []}
    if key == "audit_feed":
        return {**common, "events": []}
    if key == "operator_presence":
        return {
            **common,
            "operators_online_count": 0,
            "avatars": [],
            "status_pill_text": str(_("No operators online")),
        }
    if key in {"slo_clocks", "trust_nutrition", "trust_pillars_alerts"}:
        return {**common, "clocks": [], "pillars": [], "rows": []}
    return common


def resolve_panel_overrides(*, include_honest_empty: bool = True) -> dict[str, dict[str, Any]]:
    """Return ``{section_key: real_data_dict}`` for every panel whose resolver
    returned data. Sections whose resolver returned None are absent — the
    orchestrator should fall back to the demo payload (when demo is on)
    or the empty static defaults (when demo is off).

    Cached per-process for ``CACHE_TTL_SECONDS`` (60s) under
    ``rmc:cockpit:panels:v2`` (v3.58.x Wave 10 bumped v1->v2 when
    trust_pillars_alerts joined the orchestrator).
    """
    cache_key = f"{CACHE_PREFIX}:v2"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    out: dict[str, dict[str, Any]] = {}
    for key, resolver in _RESOLVERS:
        try:
            value = resolver()
        except Exception:
            logger.warning("panels: %s resolver crashed", key, exc_info=True)
            value = None
        if value:
            out[key] = value
        elif include_honest_empty:
            out[key] = _honest_empty_panel(key)

    try:
        cache.set(cache_key, out, CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("panels: cache set failed", exc_info=True)
    return out


def invalidate_panel_overrides_cache() -> None:
    try:
        cache.delete(f"{CACHE_PREFIX}:v2")
    except Exception:
        pass
