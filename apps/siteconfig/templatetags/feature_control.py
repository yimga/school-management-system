"""
Phase D: Template tags to hide or show UI based on school feature (plan/addon) flags.
Use when a block should only render when the school has the feature enabled.
Sidebar already filters by school.has_feature(); use these tags for in-page sections or links.
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
        return bool(school.has_feature(feature_code))
    except Exception:
        return False


