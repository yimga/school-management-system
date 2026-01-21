from django import template

register = template.Library()


@register.filter
def has_feature_permission(user, code):
    if not hasattr(user, "has_feature_permission"):
        return False
    return user.has_feature_permission(code)
