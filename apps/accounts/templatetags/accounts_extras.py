from django import template
from django.db import DatabaseError, connection, transaction
from django.db.transaction import TransactionManagementError

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
    except (DatabaseError, TransactionManagementError):
        _reset_db_state()
        return False


@register.filter
def has_role(user, code):
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.accounts.permissions import has_role as _has_role
    try:
        return _has_role(user, (code or "").strip())
    except Exception:
        _reset_db_state()
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
    from apps.accounts.permissions import has_role as _has_role
    try:
        return any(_has_role(user, c) for c in code_list)
    except Exception:
        _reset_db_state()
        return False
