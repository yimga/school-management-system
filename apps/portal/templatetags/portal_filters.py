from django import template

register = template.Library()


@register.filter
def status_color(value, threshold="80"):
    """
    Return status color (danger, warning, success) based on numeric value and threshold.

    Usage: {{ score|status_color:"70" }}
    - Danger (red): < threshold - 10
    - Warning (yellow): threshold - 10 to threshold
    - Success (green): > threshold
    """
    try:
        score = float(value)
        threshold = float(threshold)

        if score >= threshold:
            return "success"
        elif score >= threshold - 10:
            return "warning"
        else:
            return "danger"
    except (ValueError, TypeError):
        return "warning"


@register.filter
def status_icon(value, threshold="80"):
    """
    Return icon for status badge based on numeric value.

    Usage: {{ score|status_icon:"85" }}
    """
    try:
        score = float(value)
        threshold = float(threshold)

        if score >= threshold:
            return "bi-check-circle"
        elif score >= threshold - 10:
            return "bi-exclamation-triangle"
        else:
            return "bi-x-circle"
    except (ValueError, TypeError):
        return "bi-dash-circle"


# Currency display: use {% load region_format %} and |format_currency in templates
# (region-aware; no duplicate filter here).


@register.filter
def is_positive(value):
    """Check if value is positive (greater than 0)."""
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return False


@register.filter(name="attr")
def attr(obj, name):
    """Read an attribute or dict key by name, including names Django templates can't access directly.

    Django blocks ``obj._foo`` (leading underscore) and ``obj.foo-bar`` (dash) in templates.
    This filter routes around both by using ``getattr`` and dict lookup.

    Usage:
      {{ badge|attr:"_evidence_report_term_id" }}
      {{ counts|attr:"in-flight" }}

    Returns empty string when the attribute / key is missing so templates degrade
    cleanly rather than KeyError-ing at render time.
    """
    if obj is None:
        return ""
    try:
        if isinstance(obj, dict):
            return obj.get(name, "")
        return getattr(obj, name, "")
    except Exception:  # noqa: BLE001 — template filter must never raise
        return ""
