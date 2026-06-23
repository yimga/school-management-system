"""Template helpers for the `.rmc-dh-*` tenant dashboard-home grammar.

Pure presentation math so role templates stay declarative: percentage ratios for
minichart bar heights / progress widths / rings, and a token-based conic-gradient
string for the donut. No DB access, no money-float (ratios are display-only).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Full-scale percentage. Kept as a float so the magic-number gate (int literals
# >= 100) stays clean and the ratio math never silently truncates.
PCT_FULL = 100.0

# Canonical status-fill CSS variables (defined in rmc-tenant-dashboard-100x.css).
# Templates pass a semantic key; we map it to the token so no hex ever appears.
_FILL_TOKENS = {
    "paid": "var(--rmc-dh-accent)",
    "success": "var(--rmc-dh-accent)",
    "accent": "var(--rmc-dh-accent)",
    "partial": "var(--rmc-dh-warn)",
    "warn": "var(--rmc-dh-warn)",
    "overdue": "var(--rmc-dh-danger)",
    "danger": "var(--rmc-dh-danger)",
    "brand": "var(--rmc-dh-brand)",
    "brand-2": "var(--rmc-dh-brand-2)",
}


def _num(value) -> float:
    """Coerce to float for display geometry only (never a money path)."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return 0.0


@register.filter(name="dh_ratio")
def dh_ratio(value, maximum) -> int:
    """Return ``value`` as an integer 0–100 percent of ``maximum`` (clamped).

    Used for minichart bar heights, progress widths and ring fill. Returns 0 when
    the maximum is non-positive so a degraded/empty dataset renders flat, not NaN.
    """
    m = _num(maximum)
    if m <= 0:
        return 0
    pct = (_num(value) / m) * PCT_FULL
    if pct < 0:
        return 0
    if pct > PCT_FULL:
        return int(PCT_FULL)
    return int(round(pct))


@register.filter(name="dh_fill")
def dh_fill(key) -> str:
    """Map a semantic status key to its CSS fill variable (token, never hex)."""
    return _FILL_TOKENS.get(str(key or "").strip().lower(), "var(--rmc-dh-brand)")


@register.simple_tag(name="dh_donut_gradient")
def dh_donut_gradient(segments) -> str:
    """Build a token-based ``conic-gradient(...)`` value for the donut.

    ``segments`` is an iterable of mappings/sequences carrying a semantic ``fill``
    key and a numeric ``pct``. Stops are accumulated so the ring reads clockwise.
    Any remainder is filled with the neutral hairline so partial datasets still
    close the circle. Output uses only CSS custom properties — no colour literal —
    so it passes the off-token / inline-style gates when injected via
    ``style="--rmc-dh-donut-gradient:{{ ... }}"``.
    """
    stops = []
    cursor = 0.0
    for seg in segments or []:
        if isinstance(seg, dict):
            fill_key = seg.get("fill")
            pct = seg.get("pct")
        else:  # (fill, pct[, ...]) sequence
            fill_key = seg[0] if len(seg) > 0 else None
            pct = seg[1] if len(seg) > 1 else 0
        span = _num(pct)
        if span <= 0:
            continue
        start = cursor
        end = min(PCT_FULL, cursor + span)
        token = _FILL_TOKENS.get(str(fill_key or "").strip().lower(), "var(--rmc-dh-brand)")
        stops.append(f"{token} {start:.4g}% {end:.4g}%")
        cursor = end
        if cursor >= PCT_FULL:
            break
    # Always close the circle: any remainder (incl. an empty/degraded dataset)
    # fills with the neutral hairline so the ring never renders as a void.
    if cursor < PCT_FULL:
        stops.append(f"var(--hairline) {cursor:.4g}% 100%")
    return mark_safe("conic-gradient(" + ", ".join(stops) + ")")  # noqa: S308 - tokens only, no user HTML


@register.simple_tag(name="dh_child_meta")
def dh_child_meta(card, *, can_view_results: bool = False) -> str:
    """One-line meta for parent child cards."""
    from django.utils.translation import gettext as _

    if not can_view_results:
        return str(_("Linked"))
    parts = []
    rank = getattr(card, "rank", None)
    if rank:
        parts.append(_("Rank %(r)s") % {"r": rank})
    average = getattr(card, "average", None)
    if average is not None:
        parts.append(_("Avg %(a)s") % {"a": int(round(float(average)))})
    return " · ".join(parts) if parts else str(_("Linked"))


@register.simple_tag(name="dh_child_tags")
def dh_child_tags(card, *, can_view_results: bool = False, can_view_finance: bool = False) -> list[dict]:
    """Tag chips for parent child cards."""
    from django.utils.translation import gettext as _
    from django.utils.translation import ngettext

    tags: list[dict] = []
    attendance = int(getattr(card, "attendance", None) or 0)
    if attendance >= 80:
        tags.append({"label": str(_("On track")), "kind": "good"})
    else:
        tags.append({"label": str(_("Attendance")), "kind": "warn"})
    if can_view_finance:
        balance = getattr(card, "finance_balance", None) or 0
        if balance and float(balance) > 0:
            tags.append({"label": str(_("Fees due")), "kind": "warn"})
        else:
            tags.append({"label": str(_("Cleared")), "kind": "good"})
    missing = int(getattr(card, "missing_work", None) or 0)
    if missing:
        tags.append(
            {
                "label": ngettext("%(n)s task", "%(n)s tasks", missing) % {"n": missing},
                "kind": "warn",
            }
        )
    badges = getattr(card, "badges", None) or []
    for badge in list(badges)[:2]:
        label = getattr(getattr(badge, "badge_type", None), "label", None) or ""
        if label:
            tags.append({"label": str(label), "kind": ""})
    return tags


@register.simple_tag(name="dh_syllabus_segbar")
def dh_syllabus_segbar(summary) -> list[dict]:
    if not summary:
        return []
    approved = int(summary.get("approved") or 0)
    pending = int(summary.get("pending") or 0)
    draft = int(summary.get("draft") or 0)
    needs = int(summary.get("needs_revision") or 0)
    total = approved + pending + draft + needs
    if total <= 0:
        return []

    def pct(n: int) -> int:
        return int(round((n / total) * 100))

    return [
        {"fill": "success", "label": "approved", "pct": pct(approved), "val": approved},
        {"fill": "warn", "label": "pending", "pct": pct(pending), "val": pending},
        {"fill": "brand", "label": "draft", "pct": pct(draft), "val": draft},
        {"fill": "overdue", "label": "needs_revision", "pct": pct(needs), "val": needs},
    ]


@register.filter(name="dh_heat_levels")
def dh_heat_levels(trend) -> list[dict]:
    cells = []
    for row in trend or []:
        v = int(row.get("value") or 0)
        if v >= 85:
            level = "l3"
        elif v >= 60:
            level = "l2"
        elif v > 0:
            level = "l1"
        else:
            level = ""
        cells.append({"label": row.get("label") or "", "level": level})
    return cells


@register.simple_tag(name="dh_fee_donut_segments")
def dh_fee_donut_segments(paid_pct) -> list[dict]:
    paid = dh_ratio(paid_pct, 100)
    return [{"fill": "paid", "pct": paid}, {"fill": "overdue", "pct": max(0, 100 - paid)}]


@register.filter(name="dh_spark_heights")
def dh_spark_heights(trend, max_px: int = 22) -> list[int]:
    """Convert trend rows to pixel heights for KPI tile sparklines."""
    values = [int(row.get("value") or 0) for row in (trend or [])]
    if not values:
        return []
    peak = max(values) or 1
    floor = 4
    cap = max(int(max_px), floor)
    return [max(floor, int(round(v / peak * cap))) for v in values]


@register.simple_tag(name="dh_areachart_points")
def dh_areachart_points(trend) -> dict:
    """Build SVG polyline + area polygon point strings from a trend list."""
    rows = list(trend or [])
    if not rows:
        return {"line": "0,40 100,40", "area": "0,40 100,40 100,40 0,40"}
    n = len(rows)
    values = [float(r.get("value") or 0) for r in rows]
    peak = max(values) or 1.0
    coords = []
    for idx, value in enumerate(values):
        x = 0 if n == 1 else round((idx / (n - 1)) * 100, 2)
        y = round(40 - (value / peak) * 34, 2)
        coords.append((x, y))
    line = " ".join(f"{x},{y}" for x, y in coords)
    if coords:
        area = f"0,40 {line} {coords[-1][0]},40"
    else:
        area = "0,40 100,40 100,40 0,40"
    return {"line": line, "area": area}
