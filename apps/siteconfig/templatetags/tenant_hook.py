"""
Request-to-Feature: {% tenant_hook 'hook_name' %} renders fragment for school if present (plan 3.20).
§2.4: Typed exception tuple for template-tag fail-soft (no broad except).
"""
from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.utils.safestring import mark_safe

from apps.platform_runtime.structured_logging import log_exception_with_context

register = template.Library()

_TENANT_HOOK_QUERY_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    DatabaseError,
)


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
    except _TENANT_HOOK_QUERY_ERRORS as e:
        log_exception_with_context(
            "tenant_hook: fragment render skipped",
            school_id=getattr(school, "id", None),
            route=getattr(context.get("request"), "path", None) if context.get("request") else None,
            extra={"hook_name": hook_name.strip().upper(), "error": str(e)},
        )
        return ""
