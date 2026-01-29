from django import template

register = template.Library()


@register.simple_tag
def report_style_label(report_style, key, default=""):
    """Resolve report_style.label(key, default) for Django templates (no method-call syntax)."""
    if report_style is None:
        return default
    return report_style.label(key, default)


@register.simple_tag
def report_style_flag(report_style, key, default=False):
    """Resolve report_style.flag(key, default) for Django templates."""
    if report_style is None:
        return default
    return report_style.flag(key, default)
