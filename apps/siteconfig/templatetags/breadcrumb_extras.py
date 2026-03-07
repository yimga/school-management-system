from django import template

register = template.Library()


@register.filter
def split(value, separator: str = "/"):
    """
    Split strings by a separator for template usage.
    Returns an empty list when the value is falsy.
    """
    if not value:
        return []
    return [segment for segment in value.split(separator) if segment]
