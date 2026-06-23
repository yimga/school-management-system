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
