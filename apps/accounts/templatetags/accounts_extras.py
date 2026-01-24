from django import template

register = template.Library()


@register.filter
def has_feature_permission(user, code):
    if not hasattr(user, "has_feature_permission"):
        return False
    return user.has_feature_permission(code)


@register.filter
def has_role(user, code):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) == code:
        return True
    if hasattr(user, "roles"):
        return user.roles.filter(code=code).exists()
    return False


@register.filter
def has_any_role(user, codes):
    if not getattr(user, "is_authenticated", False):
        return False
    if not codes:
        return False
    code_list = [c.strip() for c in str(codes).split(",") if c.strip()]
    if not code_list:
        return False
    if getattr(user, "role", None) in code_list:
        return True
    if hasattr(user, "roles"):
        return user.roles.filter(code__in=code_list).exists()
    return False
