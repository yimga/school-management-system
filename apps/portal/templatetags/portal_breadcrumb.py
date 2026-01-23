from django import template

register = template.Library()


@register.filter
def split(value, delimiter="/"):
    """Split strings inside templates while skipping empty segments."""
    if value is None:
        return []

    try:
        parts = str(value).split(delimiter)
    except Exception:
        return []

    return [segment for segment in parts if segment]


@register.filter
def replace(value, old, new=""):
    """Simple replace filter for breadcrumb labels."""
    if value is None:
        return ""

    try:
        return str(value).replace(old, new)
    except Exception:
        return value
