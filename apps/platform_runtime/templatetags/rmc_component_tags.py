"""Type-safe helpers for shared RunMyCampus components."""

from collections.abc import Mapping

from django import template

register = template.Library()


@register.filter
def valid_metric_items(value, limit=8):
    """Return a bounded list of metric mappings; reject scalar/string inputs."""
    if isinstance(value, (str, bytes, Mapping)) or value is None:
        return []
    try:
        items = list(value)
        cap = max(0, min(int(limit), 8))
    except (TypeError, ValueError):
        return []
    if not all(isinstance(item, Mapping) for item in items):
        return []
    return items[:cap]
