from django import template

register = template.Library()


@register.filter
def split(value, delimiter="/"):
    """Split strings inside templates while skipping empty segments."""
    if value is None:
        return []

    try:
        parts = str(value).split(delimiter)
    except (TypeError, AttributeError, ValueError):
        return []

    return [segment for segment in parts if segment]


@register.filter
def breadcrumb_label(value):
    """Convert slug/path parts into human-readable text (spaces + title case)."""
    if value is None:
        return ""

    try:
        label = str(value)
        label = label.replace("_", " ").replace("-", " ")
        return label.title()
    except (TypeError, AttributeError, ValueError):
        return value
