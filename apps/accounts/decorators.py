from django.contrib.auth.decorators import user_passes_test


def _has_any_role(user, roles: tuple[str, ...]) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) in roles:
        return True
    return user.roles.filter(code__in=roles).exists()


def role_required(*roles: str):
    def check(user):
        return _has_any_role(user, roles)
    return user_passes_test(check)


def permission_required(*codes: str):
    def check(user):
        if not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return any(user.has_feature_permission(code) for code in codes)
    return user_passes_test(check)
