"""
Request-to-Feature: {% tenant_hook 'hook_name' %} renders fragment for school if present (plan 3.20).
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def tenant_hook(context, hook_name: str):
    """
    If the current school has a FeatureFragment for this hook, return its content (or placeholder).
    Otherwise return empty string. Use in templates: {% tenant_hook 'STUDENT_PROFILE_SIDEBAR' %}
    """
    school = context.get("school") or context.get("request") and getattr(context["request"], "school", None)
    if not school:
        return ""
    try:
        from apps.siteconfig.models import FeatureFragment
        frag = FeatureFragment.objects.filter(
            school=school,
            target_hook=hook_name.strip().upper(),
            is_active=True,
        ).first()
        if not frag:
            return ""
        # Render metadata_schema: could be {"html": "<div>..."} or inject a partial path
        schema = frag.metadata_schema or {}
        if isinstance(schema.get("html"), str):
            return mark_safe(schema["html"])
        if schema.get("partial"):
            # Optional: load HTMX partial by name
            return ""
        return ""
    except Exception:
        return ""
