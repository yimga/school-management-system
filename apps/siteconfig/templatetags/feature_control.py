"""
Phase D: Template tags to hide or show UI based on school feature (plan/addon) flags.
Use when a block should only render when the school has the feature enabled.
Uses Policy Registry (is_feature_enabled) — no direct school.has_feature in templates.
"""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def feature_enabled(context, feature_code: str) -> bool:
    """
    Return True if the current school has the given feature enabled (plan or addon).
    Usage: {% feature_enabled "design_studio" as has_design_studio %} ... {% if has_design_studio %}...{% endif %}
    """
    request = context.get("request")
    school = getattr(request, "school", None) if request else None
    if not school:
        return False
    try:
        from apps.schools.models import is_feature_enabled
        return bool(is_feature_enabled(school, feature_code))
    except Exception:
        return False


