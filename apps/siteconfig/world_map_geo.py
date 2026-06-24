"""Geo helpers for the cockpit live world map (lat/lng markers on the 3D globe).

Resolution order per school row:
  1. ``settings.location`` explicit latitude/longitude (provisioning payload)
  2. ``settings.location.city_id`` via ``GlobalGeoCatalog.get_city``
  3. ``settings.location.city`` / ``label`` via ``GlobalGeoCatalog.search_cities``
  4. Country centroid (largest catalog city) + deterministic jitter
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.siteconfig.global_catalog import GlobalGeoCatalog

# Status colours — must stay aligned with templates/partials/cockpit/_live_world_map.html
# status key legend and rmc-cp-200x.css pulse tokens.
STATUS_COLORS: dict[str, dict[str, str]] = {
    "active": {"color": "#6ee7b7", "ring_color": "#10b981", "label": str(_("Active"))},
    "suspended": {"color": "#fcd34d", "ring_color": "#f59e0b", "label": str(_("Suspended"))},
    "frozen": {"color": "#93c5fd", "ring_color": "#3b82f6", "label": str(_("Frozen"))},
}

_WORLD_BUCKET_FOR = {
    "US": "North America", "CA": "North America", "MX": "North America",
    "NG": "West Africa", "GH": "West Africa", "CM": "West Africa",
    "SL": "West Africa", "CI": "West Africa", "SN": "West Africa",
    "GB": "Europe", "FR": "Europe", "DE": "Europe", "IE": "Europe",
    "AU": "Asia · Oceania", "NZ": "Asia · Oceania", "IN": "Asia · Oceania",
    "SG": "Asia · Oceania", "PH": "Asia · Oceania",
}

REGION_CENTROIDS: dict[str, dict[str, float]] = {
    "North America": {"lat": 42.0, "lng": -98.0, "altitude": 1.02},
    "West Africa": {"lat": 8.0, "lng": 2.0, "altitude": 1.02},
    "Europe": {"lat": 50.0, "lng": 10.0, "altitude": 1.02},
    "Asia · Oceania": {"lat": 15.0, "lng": 105.0, "altitude": 1.02},
    "Other": {"lat": 0.0, "lng": 0.0, "altitude": 1.02},
}

# Lab parity (globe-void-ai-lab core fix #1): equatorial fill-frame default when fleet is empty.
DEFAULT_GLOBE_CAMERA: dict[str, float] = {"lat": 8.0, "lng": -5.0, "altitude": 1.02}
GLOBE_FILL_ALTITUDE = 1.02


def compute_default_camera(markers: list[dict[str, Any]]) -> dict[str, float]:
    """Center the globe on live fleet pins at fill-frame altitude (not polar-skewed)."""
    points = [
        m
        for m in markers
        if m.get("lat") is not None
        and m.get("lng") is not None
        and not m.get("is_cluster")
        and m.get("status") not in ("ghost",)
    ]
    if not points:
        return dict(DEFAULT_GLOBE_CAMERA)
    lat_sum = 0.0
    lng_sum = 0.0
    for m in points:
        lat_sum += float(m["lat"])
        lng_sum += float(m["lng"])
    n = len(points)
    lat = max(-25.0, min(35.0, lat_sum / n))
    lng = lng_sum / n
    if lng > 180.0:
        lng -= 360.0
    if lng < -180.0:
        lng += 360.0
    return {"lat": round(lat, 2), "lng": round(lng, 2), "altitude": GLOBE_FILL_ALTITUDE}

# Per-region watercolor tints for WebGL polygon caps, labels, and HQ arcs.
REGION_PALETTE: dict[str, dict[str, str]] = {
    "North America": {
        "cap": "rgba(52,211,153,0.14)",
        "cap_highlight": "rgba(52,211,153,0.36)",
        "cap_dim": "rgba(20,50,40,0.05)",
        "label": "rgba(110,231,183,0.95)",
        "label_country": "rgba(167,243,208,0.82)",
        "arc": "rgba(52,211,153,0.52)",
        "side": "rgba(16,185,129,0.22)",
    },
    "West Africa": {
        "cap": "rgba(251,191,36,0.14)",
        "cap_highlight": "rgba(251,191,36,0.38)",
        "cap_dim": "rgba(60,45,10,0.05)",
        "label": "rgba(253,224,71,0.95)",
        "label_country": "rgba(254,240,138,0.82)",
        "arc": "rgba(251,191,36,0.52)",
        "side": "rgba(245,158,11,0.22)",
    },
    "Europe": {
        "cap": "rgba(129,140,248,0.14)",
        "cap_highlight": "rgba(129,140,248,0.38)",
        "cap_dim": "rgba(30,30,60,0.05)",
        "label": "rgba(165,180,252,0.95)",
        "label_country": "rgba(199,210,254,0.82)",
        "arc": "rgba(129,140,248,0.52)",
        "side": "rgba(99,102,241,0.22)",
    },
    "Asia · Oceania": {
        "cap": "rgba(244,114,182,0.14)",
        "cap_highlight": "rgba(244,114,182,0.38)",
        "cap_dim": "rgba(60,20,40,0.05)",
        "label": "rgba(249,168,212,0.95)",
        "label_country": "rgba(251,207,232,0.82)",
        "arc": "rgba(244,114,182,0.52)",
        "side": "rgba(236,72,153,0.22)",
    },
    "Other": {
        "cap": "rgba(148,163,184,0.11)",
        "cap_highlight": "rgba(148,163,184,0.30)",
        "cap_dim": "rgba(40,45,55,0.05)",
        "label": "rgba(203,213,225,0.88)",
        "label_country": "rgba(203,213,225,0.72)",
        "arc": "rgba(148,163,184,0.42)",
        "side": "rgba(100,116,139,0.18)",
    },
}

# SVG fallback label anchors (600×280 viewBox) — must match cockpit regional blobs.
SVG_REGION_LABELS: dict[str, dict[str, float]] = {
    "North America": {"svg_x": 112, "svg_y": 96},
    "Europe": {"svg_x": 214, "svg_y": 92},
    "West Africa": {"svg_x": 244, "svg_y": 132},
    "Asia · Oceania": {"svg_x": 416, "svg_y": 118},
    "Other": {"svg_x": 300, "svg_y": 148},
}

# Schematic offline SVG land blobs → region bucket (matches template path order).
SVG_LAND_REGIONS: tuple[str, ...] = (
    "North America",
    "Europe",
    "West Africa",
    "Asia · Oceania",
)

SVG_VIEWBOX_WIDTH = 600.0
SVG_VIEWBOX_HEIGHT = 280.0

GLOBE_EARTH_TEXTURE_URL = "/static/img/globe/earth-night-1k.jpg"

# Platform HQ anchor for arc visualization (configurable via env in future waves).
DEFAULT_HQ = {"lat": 6.52, "lng": 3.38, "label": "Platform HQ"}

# Low-discrepancy unit offsets — same pattern as cockpit_panels_realdata_service.
_SPREAD_UNIT = [
    (0.0, 0.0), (0.62, 0.30), (-0.55, 0.42), (0.40, -0.55), (-0.72, -0.25), (0.86, 0.56),
    (-0.34, 0.72), (0.55, 0.64), (-0.86, 0.46), (0.22, -0.80), (0.74, -0.40), (-0.60, -0.64),
]

# Degrees — small enough to keep pins inside country-ish bounds after jitter.
_JITTER_DEG = 0.85
_JITTER_PRECISE_DEG = 0.12

_CLUSTER_ZOOM_THRESHOLD = 2.2
_CLUSTER_CELL_DEG = 6.0


def _location_dict(row: dict[str, Any]) -> dict[str, Any]:
    settings = row.get("settings")
    if not isinstance(settings, dict):
        return {}
    loc = settings.get("location")
    return loc if isinstance(loc, dict) else {}


def resolve_school_country_alpha2(row: dict[str, Any]) -> str:
    """Resolve ISO alpha-2 from school.country_code or settings.location hints."""
    raw = (row.get("country_code") or "").strip()
    if raw:
        a2 = GlobalGeoCatalog.alpha2_for_country(raw.upper())
        if a2:
            return a2
        if len(raw) == 2:
            return raw.upper()

    loc = _location_dict(row)
    for key in ("country_code", "country", "country_id"):
        val = (loc.get(key) or "").strip()
        if not val:
            continue
        a2 = GlobalGeoCatalog.alpha2_for_country(val.upper())
        if a2:
            return a2
        if len(val) == 2:
            return val.upper()
        name_key = val.casefold()
        for country_row in GlobalGeoCatalog.list_countries():
            if (country_row.get("name") or "").casefold() == name_key:
                return GlobalGeoCatalog.alpha2_for_country(country_row["code"])
    return ""


def region_for_country(alpha2: str) -> str:
    return _WORLD_BUCKET_FOR.get((alpha2 or "").upper(), "Other")


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _resolve_school_coords(row: dict[str, Any]) -> tuple[float, float, str | None, bool] | None:
    """Return (lat, lng, city_label, precise) or None when geography is unknown."""
    cc = resolve_school_country_alpha2(row)
    loc = _location_dict(row)
    city_label = (loc.get("city") or loc.get("label") or "").strip() or None

    lat = _float_or_none(loc.get("latitude") if "latitude" in loc else loc.get("lat"))
    lng = _float_or_none(loc.get("longitude") if "longitude" in loc else loc.get("lng"))
    if lat is not None and lng is not None:
        return lat, lng, city_label, True

    city_id = (loc.get("city_id") or "").strip()
    if city_id:
        city_row = GlobalGeoCatalog.get_city(city_id, country_code=cc or None)
        if city_row:
            return (
                float(city_row["latitude"]),
                float(city_row["longitude"]),
                city_row.get("label") or city_label,
                True,
            )

    city_query = city_label or ""
    if city_query and cc:
        hits = GlobalGeoCatalog.search_cities(country_code=cc, query=city_query, limit=1)
        if hits:
            top = hits[0]
            return (
                float(top["latitude"]),
                float(top["longitude"]),
                top.get("label") or city_query,
                True,
            )

    centroid = _country_centroid(cc) if cc else None
    if centroid is None:
        return None
    return centroid[0], centroid[1], city_label, False


def _country_centroid(alpha2: str) -> tuple[float, float] | None:
    """Return (lat, lng) for the largest catalog city in the country, or None."""
    alpha3 = GlobalGeoCatalog.normalize_country_code(alpha2)
    if not alpha3:
        return None
    country_index, _, _ = GlobalGeoCatalog._build_city_indexes()  # noqa: SLF001
    rows = country_index.get(alpha3) or []
    if not rows:
        return None
    top = rows[0]
    lat = float(top.get("latitude") or 0.0)
    lng = float(top.get("longitude") or 0.0)
    if not lat and not lng:
        return None
    return lat, lng


def _deterministic_jitter(country_code: str, slot: int) -> tuple[float, float]:
    """Stable sub-degree offset from country + slot index."""
    seed = hashlib.sha256(f"{country_code}:{slot}".encode()).digest()
    ux = (_SPREAD_UNIT[slot % len(_SPREAD_UNIT)][0])
    uy = (_SPREAD_UNIT[slot % len(_SPREAD_UNIT)][1])
    hx = (seed[0] / 255.0 - 0.5) * 0.35
    hy = (seed[1] / 255.0 - 0.5) * 0.35
    return ux * _JITTER_DEG + hx, uy * _JITTER_DEG + hy


def _status_for_row(row: dict[str, Any]) -> str:
    if row.get("is_frozen"):
        return "frozen"
    if row.get("is_active") is False:
        return "suspended"
    return "active"


def _format_last_sync_label(updated_at: Any) -> str | None:
    """Human-readable sync hint for globe pin tooltips (PII-safe, no raw timestamps in API)."""
    if updated_at is None:
        return None
    try:
        from django.utils import timezone
        from django.utils.timesince import timesince

        if timezone.is_naive(updated_at):
            updated_at = timezone.make_aware(updated_at, timezone.get_current_timezone())
        delta = timesince(updated_at, timezone.now())
        return f"{delta} ago" if delta else None
    except Exception:
        return None


def build_globe_markers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build lat/lng marker dicts for the interactive globe from school rows."""
    per_country: dict[str, int] = {}
    markers: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        cc = resolve_school_country_alpha2(row)
        resolved = _resolve_school_coords(row)
        if resolved is None:
            continue
        slot = per_country.get(cc, 0)
        per_country[cc] = slot + 1
        lat0, lng0, city_label, precise = resolved
        dlat, dlng = _deterministic_jitter(cc or "XX", slot)
        jitter_scale = (_JITTER_PRECISE_DEG / _JITTER_DEG) if precise else 1.0
        status = _status_for_row(row)
        palette = STATUS_COLORS[status]
        region = region_for_country(cc)
        country_name = GlobalGeoCatalog.country_name(cc) if cc else ""
        marker: dict[str, Any] = {
            "lat": round(lat0 + dlat * jitter_scale, 5),
            "lng": round(lng0 + dlng * jitter_scale, 5),
            "country_code": cc,
            "country_name": country_name,
            "status": status,
            "color": palette["color"],
            "ring_color": palette["ring_color"],
            "label": palette["label"],
            "region": region,
            "delay_s": round((i % 12) * 0.18, 2),
        }
        if city_label:
            marker["city"] = city_label
        school_id = row.get("id")
        if school_id is not None:
            marker["school_id"] = str(school_id)
        name = (row.get("name") or row.get("slug") or "").strip()
        if name:
            marker["name"] = name
        slug = (row.get("slug") or "").strip()
        if slug:
            marker["slug"] = slug
        plan_tier = (row.get("plan__name") or row.get("plan_name") or "").strip()
        if plan_tier:
            marker["plan_tier"] = plan_tier
        sync_label = _format_last_sync_label(row.get("updated_at"))
        if sync_label:
            marker["last_sync_label"] = sync_label
        markers.append(marker)
    return markers


def filter_markers(
    markers: list[dict[str, Any]],
    *,
    region: str | None = None,
    status: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict[str, Any]]:
    """Filter markers by region, status, and optional lat/lng bounding box."""
    out = markers
    if region:
        out = [m for m in out if m.get("region") == region]
    if status:
        out = [m for m in out if m.get("status") == status]
    if bbox:
        lat_min, lat_max, lng_min, lng_max = bbox
        out = [
            m for m in out
            if lat_min <= float(m["lat"]) <= lat_max and lng_min <= float(m["lng"]) <= lng_max
        ]
    return out


def cluster_markers(markers: list[dict[str, Any]], *, zoom: float) -> list[dict[str, Any]]:
    """Grid-cluster markers when zoomed out; returns individual pins when zoomed in."""
    if zoom >= _CLUSTER_ZOOM_THRESHOLD or len(markers) <= 12:
        return markers

    cell = _CLUSTER_CELL_DEG / max(zoom, 0.6)
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for m in markers:
        key = (math.floor(float(m["lat"]) / cell), math.floor(float(m["lng"]) / cell))
        buckets.setdefault(key, []).append(m)

    clustered: list[dict[str, Any]] = []
    for group in buckets.values():
        if len(group) == 1:
            clustered.append(group[0])
            continue
        lat = sum(float(g["lat"]) for g in group) / len(group)
        lng = sum(float(g["lng"]) for g in group) / len(group)
        region = group[0].get("region") or "Other"
        clustered.append({
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "region": region,
            "country_code": group[0].get("country_code") or "",
            "status": "active",
            "color": "#a5b4fc",
            "ring_color": "#6366f1",
            "label": str(_("Cluster")),
            "is_cluster": True,
            "cluster_count": len(group),
            "cluster_members": [
                {"school_id": g.get("school_id"), "name": g.get("name"), "slug": g.get("slug"), "status": g.get("status")}
                for g in group[:12]
            ],
            "point_radius": min(1.2, 0.42 + len(group) * 0.04),
        })
    return clustered


def _build_arcs(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HQ → regional centroid arcs for schools active in each region."""
    hq = DEFAULT_HQ
    regions_seen: set[str] = set()
    arcs: list[dict[str, Any]] = []
    for m in markers:
        region = m.get("region") or "Other"
        if region in regions_seen:
            continue
        regions_seen.add(region)
        centroid = REGION_CENTROIDS.get(region, REGION_CENTROIDS["Other"])
        palette = REGION_PALETTE.get(region, REGION_PALETTE["Other"])
        arcs.append({
            "start_lat": hq["lat"],
            "start_lng": hq["lng"],
            "end_lat": centroid["lat"],
            "end_lng": centroid["lng"],
            "color": palette["arc"],
            "region": region,
        })
    return arcs


def _build_tour_waypoints(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Camera waypoints visiting each populated region."""
    by_region: dict[str, int] = {}
    for m in markers:
        region = m.get("region") or "Other"
        by_region[region] = by_region.get(region, 0) + 1
    waypoints: list[dict[str, Any]] = []
    for region, count in sorted(by_region.items(), key=lambda item: item[1], reverse=True):
        centroid = REGION_CENTROIDS.get(region, REGION_CENTROIDS["Other"])
        waypoints.append({
            "lat": centroid["lat"],
            "lng": centroid["lng"],
            "altitude": GLOBE_FILL_ALTITUDE,
            "label": region,
            "caption": str(_("%(region)s — %(count)s schools") % {"region": region, "count": count}),
            "dwell_ms": 3200,
        })
    return waypoints


def _build_iso3_region_map() -> dict[str, str]:
    """Map ISO-3166 alpha-3 codes to platform region buckets (polygon tinting)."""
    out: dict[str, str] = {}
    for alpha2, region in _WORLD_BUCKET_FOR.items():
        alpha3 = GlobalGeoCatalog.normalize_country_code(alpha2)
        if alpha3:
            out[alpha3] = region
    return out


def _build_region_labels(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Floating continent/region labels for the WebGL globe."""
    counts: dict[str, int] = {}
    for m in markers:
        region = m.get("region") or "Other"
        counts[region] = counts.get(region, 0) + 1
    labels: list[dict[str, Any]] = []
    for region, count in counts.items():
        centroid = REGION_CENTROIDS.get(region, REGION_CENTROIDS["Other"])
        palette = REGION_PALETTE.get(region, REGION_PALETTE["Other"])
        labels.append({
            "lat": centroid["lat"],
            "lng": centroid["lng"],
            "text": f"{region} ({count})",
            "region": region,
            "count": count,
            "kind": "region",
            "size": 0.58,
            "color": palette["label"],
        })
    return labels


def lat_lng_to_svg(lat: float, lng: float) -> dict[str, float]:
    """Project WGS84 coords into the offline SVG viewBox."""
    x = (float(lng) + 180.0) / 360.0 * SVG_VIEWBOX_WIDTH
    y = (90.0 - float(lat)) / 180.0 * SVG_VIEWBOX_HEIGHT
    return {
        "svg_x": round(max(24.0, min(SVG_VIEWBOX_WIDTH - 24.0, x)), 1),
        "svg_y": round(max(14.0, min(SVG_VIEWBOX_HEIGHT - 14.0, y)), 1),
    }


def _build_country_labels(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Country names only where tenants exist — avoids flat-map label clutter."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for m in markers:
        if m.get("is_cluster"):
            continue
        cc = (m.get("country_code") or "").upper()
        if not cc:
            continue
        buckets.setdefault(cc, []).append(m)
    labels: list[dict[str, Any]] = []
    for cc, group in buckets.items():
        lat = sum(float(g["lat"]) for g in group) / len(group)
        lng = sum(float(g["lng"]) for g in group) / len(group)
        region = group[0].get("region") or "Other"
        palette = REGION_PALETTE.get(region, REGION_PALETTE["Other"])
        name = (group[0].get("country_name") or cc).strip()
        text = name if len(group) == 1 else f"{name} ({len(group)})"
        labels.append({
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "text": text,
            "region": region,
            "country_code": cc,
            "kind": "country",
            "size": 0.36,
            "color": palette["label_country"],
            **lat_lng_to_svg(lat, lng),
        })
    return labels


def enrich_regional_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach SVG label coordinates + region palette colors for offline map parity."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        label = row.get("label") or row.get("region") or ""
        anchor = SVG_REGION_LABELS.get(label, SVG_REGION_LABELS["Other"])
        palette = REGION_PALETTE.get(label, REGION_PALETTE["Other"])
        centroid = REGION_CENTROIDS.get(label, REGION_CENTROIDS["Other"])
        enriched.append({
            **row,
            "svg_x": anchor["svg_x"],
            "svg_y": anchor["svg_y"],
            "label_color": palette["label"],
            "land_color": palette["cap"],
            "fly_lat": centroid["lat"],
            "fly_lng": centroid["lng"],
        })
    return enriched


def _build_expansion_targets(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """GLOCAL ghost pins for regions with zero live schools (Wow+ radar)."""
    populated: set[str] = set()
    for m in markers:
        region = m.get("region") or ""
        if region and not m.get("is_cluster"):
            populated.add(region)
    targets: list[dict[str, Any]] = []
    for region, centroid in REGION_CENTROIDS.items():
        if region in populated or region == "Other":
            continue
        targets.append({
            "lat": centroid["lat"],
            "lng": centroid["lng"],
            "name": str(_("%(region)s target") % {"region": region}),
            "region": region,
            "status": "ghost",
            "color": "rgba(148,163,184,0.5)",
            "ring_color": "rgba(148,163,184,0.35)",
        })
    return targets


def build_globe_payload(
    markers: list[dict[str, Any]],
    *,
    auto_rotate: bool = True,
    auto_rotate_speed: float = 0.35,
    layout: str = "hero",
    tour_enabled: bool = True,
) -> dict[str, Any]:
    """Theme + marker bundle consumed by the front-end globe island."""
    return {
        "markers": markers,
        "theme": {
            "atmosphere": "rgba(129,140,248,0.42)",
            "globeColor": "#0c1228",
            "globeEmissive": "#1a1640",
            "polygonCap": "rgba(148,163,184,0.10)",
            "polygonSide": "rgba(99,102,241,0.14)",
            "polygonStroke": "rgba(148,163,184,0.24)",
            "polygonCapDim": "rgba(71,85,105,0.06)",
            "polygonCapHighlight": "rgba(129,140,248,0.22)",
        },
        "geo_url": "/static/geo/world-countries-110m.json",
        "globe_texture_url": GLOBE_EARTH_TEXTURE_URL,
        "label_zoom": {
            "country_fade_start": 1.15,
            "country_fade_end": 1.55,
        },
        "auto_rotate": auto_rotate,
        "auto_rotate_speed": auto_rotate_speed,
        "camera": compute_default_camera(markers),
        "layout": layout if layout in ("hero", "side") else "hero",
        "tour_enabled": bool(tour_enabled),
        "region_centroids": REGION_CENTROIDS,
        "region_labels": _build_region_labels(markers),
        "country_labels": _build_country_labels(markers),
        "region_palette": REGION_PALETTE,
        "iso3_region_map": _build_iso3_region_map(),
        "hq": DEFAULT_HQ,
        "arcs": _build_arcs(markers),
        "tour_waypoints": _build_tour_waypoints(markers) if tour_enabled else [],
        "expansion_targets": _build_expansion_targets(markers),
        "api": {
            "markers": "/super/api/globe/markers/",
            "stream": "/super/api/globe/stream/",
            "live": "/super/api/globe/live/",
            "operator_fleet_stream": "/super/api/operator/fleet/stream/",
            "operator_fleet_snapshot": "/super/api/operator/fleet/snapshot/",
            "operator_fleet_context": "/super/api/operator/fleet/context/",
            "operator_fleet_globe_presence": "/super/api/operator/fleet/globe-presence/",
            "operator_fleet_tour_narrator": "/super/api/operator/fleet/tour-narrator/",
        },
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
            "day_night_terminator": True,
            "tour_narrator": True,
            "first_visit_fly_in": True,
            "cluster_bloom": True,
            "compact_guide_max_schools": 5,
            "day_arc": True,
            "context_lens": True,
            "pulse_timeline": True,
            "hero_metric": True,
            "glass_dock": True,
            "constellation_mode": True,
            "orbit_chips": True,
        },
        "live_refresh": {
            "sse_interval_seconds": 5,
            "poll_interval_ms": 5000,
            "sse_reconnect_ms": 4000,
        },
    }


def compute_globe_revision(markers: list[dict[str, Any]]) -> str:
    """Stable fingerprint for live refresh — changes when pins or status change."""
    parts = sorted(
        f"{m.get('school_id') or ''}:{m.get('status') or ''}:{m.get('lat')}:{m.get('lng')}"
        for m in markers
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def build_globe_live_bundle(
    markers: list[dict[str, Any]],
    *,
    zoom: float = 1.02,
    region: str | None = None,
    status: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Markers + labels + arcs bundle for live API refresh (pre-clustered for zoom)."""
    filtered = filter_markers(markers, region=region, status=status, bbox=bbox)
    country_labels = _build_country_labels(filtered)
    clustered = cluster_markers(filtered, zoom=zoom)
    return {
        "revision": compute_globe_revision(filtered),
        "markers": clustered,
        "country_labels": country_labels,
        "region_labels": _build_region_labels(filtered),
        "arcs": _build_arcs(filtered),
        "tour_waypoints": _build_tour_waypoints(filtered),
        "marker_count": len(filtered),
        "display_count": len(clustered),
    }
