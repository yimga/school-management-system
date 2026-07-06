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
    except (DatabaseError, TransactionManagementError):
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
    except (DatabaseError, TransactionManagementError, AttributeError, TypeError):
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
    except (DatabaseError, TransactionManagementError, AttributeError, TypeError):
        _reset_db_state()
        return False


@register.filter
def tenant_operator_hub_visible(user):
    """True when tenant portal should show operator strip + studio product rail."""
    from apps.accounts.permissions import tenant_operator_hub_eligible

    return tenant_operator_hub_eligible(user)


@register.simple_tag(takes_context=True)
def can_access_permission(context, *codes):
    """True if the current user may reach a surface gated on ANY of ``codes`` (additive:
    a granted code OR the tenant-admin tier). Drives per-section RBAC hide/show so a config
    surface renders only the sections the viewer can actually open.

    Usage: ``{% can_access_permission "finance.view" "finance.manage" as can_finance %}``.
    Fails closed (hidden) on any error."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if connection.needs_rollback:
        _reset_db_state()
        return False
    try:
        from apps.accounts.effective_access import permission_access

        return permission_access(
            user, getattr(request, "school", None), tuple(codes)
        )
    except (DatabaseError, TransactionManagementError, AttributeError, TypeError, ValueError):
        _reset_db_state()
        return False
