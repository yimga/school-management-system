"""Sparkline rendering service — v3.57.0 (2026-05-21).

Pure-Python SVG sparkline builder used by the cockpit `_pulse_metrics.html`
partial and the v3.57.0 front-office 200x elements (revenue cohort, NPS
ticker, support burndown, capacity planning, churn scorecard).

The helpers are intentionally DB-free and view-free:

  * `render_sparkline_svg(values, ...)` — converts a list of numeric samples
    into an inline SVG string that the template embeds via `{{ svg|safe }}`.
  * `format_sparkline_meta(values)` — derives the headline number + delta
    label + delta direction the partial already supports.

The shape returned by `format_sparkline_meta` matches the v3.56 manager
pulse-card schema (head / value / label / delta / delta_direction) so the
existing partial renders without modification.

PII safety: no user / tenant identifiers ever land in the SVG or the meta
dict. Callers pass a list of pure numbers; this module never reaches the
ORM or the request.

Determinism: with the same inputs the SVG bytes are byte-stable (no random
ids, no datetime stamps).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Sequence

__all__ = [
    "render_sparkline_svg",
    "format_sparkline_meta",
    "SparklineError",
]


class SparklineError(ValueError):
    """Raised when the input series can't be rendered to a sparkline."""


_DEFAULT_WIDTH = 120
_DEFAULT_HEIGHT = 32
_DEFAULT_STROKE = 1.5
_DEFAULT_PADDING = 2.0


def _coerce_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError as exc:
            raise SparklineError(f"non-numeric sample: {value!r}") from exc
    raise SparklineError(f"unsupported sample type: {type(value).__name__}")


def _normalize_series(values: Sequence[Any]) -> list[float]:
    if not values:
        raise SparklineError("empty series")
    out: list[float] = []
    for v in values:
        if v is None:
            # Honest "no sample yet" — render as the previous value (carry forward).
            if out:
                out.append(out[-1])
            else:
                out.append(0.0)
            continue
        out.append(_coerce_float(v))
    return out


def render_sparkline_svg(
    values: Sequence[Any],
    *,
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    stroke_width: float = _DEFAULT_STROKE,
    color: str = "currentColor",
    fill: str | None = None,
    aria_label: str | None = None,
) -> str:
    """Return an inline SVG string rendering `values` as a sparkline.

    All color values default to `currentColor` so the consuming page's text
    color cascades correctly under any tenant brand or operator dark-chrome.
    Pass an explicit `color="..."` to opt out (rare; usually wrong).

    `aria_label` is rendered as a `<title>` child for screen-reader support.
    Without one the SVG is `aria-hidden="true"` (purely decorative).
    """
    series = _normalize_series(values)
    if width <= 0 or height <= 0:
        raise SparklineError("width and height must be positive")

    lo = min(series)
    hi = max(series)
    rng = hi - lo if hi != lo else 1.0
    n = len(series)
    if n == 1:
        # Single point — render a horizontal dash mid-height.
        y = height / 2
        path = f"M{_DEFAULT_PADDING:.2f},{y:.2f} L{width - _DEFAULT_PADDING:.2f},{y:.2f}"
    else:
        step = (width - 2 * _DEFAULT_PADDING) / (n - 1)
        points: list[str] = []
        for i, v in enumerate(series):
            x = _DEFAULT_PADDING + i * step
            # Invert Y so high values plot at top.
            y = _DEFAULT_PADDING + (1 - ((v - lo) / rng)) * (height - 2 * _DEFAULT_PADDING)
            points.append(f"{x:.2f},{y:.2f}")
        path = "M" + " L".join(points)

    accessibility = (
        f'role="img" aria-label="{aria_label}"'
        if aria_label
        else 'role="presentation" aria-hidden="true"'
    )
    title_node = f"<title>{aria_label}</title>" if aria_label else ""
    fill_attr = f'fill="{fill}"' if fill else 'fill="none"'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'{accessibility}>'
        f"{title_node}"
        f'<path d="{path}" {fill_attr} stroke="{color}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
        f"</svg>"
    )


def _format_value(v: float) -> str:
    """Format the headline number — strip trailing zeros and unnecessary `.0`."""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{v / 1_000:.1f}k".replace(".0k", "k")
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.1f}"


def format_sparkline_meta(
    values: Sequence[Any],
    *,
    head: str = "",
    label: str = "",
    severity: str = "info",
    value_formatter: Any = None,
) -> dict[str, Any]:
    """Return a dict matching the cockpit pulse-card / sparkline schema.

    Shape (matches `_pulse_metrics.html` partial):
        head             str  — caption (e.g. "Schools")
        value            str  — headline number, e.g. "1.2k"
        label            str  — sub-caption, e.g. "Healthy"
        severity         str  — ok / warn / danger / info
        delta            str  — absolute change formatted, e.g. "+12"
        delta_direction  str  — up / down / flat
        sparkline_svg    str  — inline SVG string
    """
    series = _normalize_series(values)
    if not series:
        raise SparklineError("empty series")

    first = series[0]
    last = series[-1]
    delta_value = last - first
    if delta_value > 0:
        delta_direction = "up"
        delta_sign = "+"
    elif delta_value < 0:
        delta_direction = "down"
        delta_sign = "-"
    else:
        delta_direction = "flat"
        delta_sign = ""

    fmt = value_formatter or _format_value
    return {
        "head": head,
        "value": fmt(last),
        "label": label,
        "severity": severity,
        "delta": f"{delta_sign}{fmt(abs(delta_value))}" if delta_value else "0",
        "delta_direction": delta_direction,
        "sparkline_svg": render_sparkline_svg(series, aria_label=head or None),
    }


# Convenience for callers that don't have a numeric series — e.g. counts
# returned from `apps.observability.metrics`.
def from_iterable(it: Iterable[Any], **kwargs: Any) -> dict[str, Any]:
    return format_sparkline_meta(list(it), **kwargs)
