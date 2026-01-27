from django import template
from django.db import DatabaseError, connection, transaction

register = template.Library()

def _reset_db_state() -> None:
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except Exception:
        pass


@register.filter
def has_feature_permission(user, code):
    if not hasattr(user, "has_feature_permission"):
        return False
    if connection.needs_rollback:
        _reset_db_state()
        return False
    try:
        return user.has_feature_permission(code)
    except DatabaseError:
        _reset_db_state()
        return False


@register.filter
def has_role(user, code):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) == code:
        return True
    if hasattr(user, "roles"):
        if connection.needs_rollback:
            _reset_db_state()
            return False
        try:
            return user.roles.filter(code=code).exists()
        except DatabaseError:
            _reset_db_state()
            return False
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
        if connection.needs_rollback:
            _reset_db_state()
            return False
        try:
            return user.roles.filter(code__in=code_list).exists()
        except DatabaseError:
            _reset_db_state()
            return False
    return False
