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
