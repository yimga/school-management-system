"""Template tags for glocal vocabulary (batch 1531)."""

from django import template

from apps.platform_runtime.glocal_vocabulary import resolve_ui_token

register = template.Library()


@register.simple_tag(takes_context=True)
def glocal_token(context, key: str, fallback: str = "") -> str:
    request = context.get("request")
    school = getattr(request, "school", None) if request else None
    return resolve_ui_token(key, school, fallback=fallback or None)
