from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden

from apps.siteconfig.models import SiteSettings


def _normalize_role(r) -> str:
    """Normalize role to uppercase string for case-insensitive comparison."""
    if hasattr(r, "value"):
        return str(r.value).strip().upper()
    if isinstance(r, str):
        return r.strip().upper()
    return str(r).strip().upper()


def _has_any_role(user, roles: tuple[str, ...]) -> bool:
    from apps.accounts.permissions import has_role
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    normalized = tuple(_normalize_role(r) for r in roles)
    for r in normalized:
        if has_role(user, r):
            return True
    return False


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


def portal_toggle_required(flag_name: str, message: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            site = SiteSettings.get_solo()
            # Only an explicit False should disable a portal; tolerate missing/None in test doubles.
            if getattr(site, flag_name, True) is False:
                return HttpResponseForbidden(message)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


parent_portal_required = portal_toggle_required("enable_parent_portal", "Parent portal is disabled.")
teacher_portal_required = portal_toggle_required("enable_teacher_portal", "Teacher portal is disabled.")


def object_permission_required(check_func, error_message="You don't have permission to access this resource."):
    """
    Decorator for object-level permission checks.
    
    Args:
        check_func: Callable that takes (request, *args, **kwargs) and returns bool
        error_message: Error message to display if permission denied
        
    Example:
        @object_permission_required(
            lambda request, invoice_id: can_access_invoice(request.user, invoice_id),
            "You cannot access this invoice."
        )
        def invoice_detail(request, invoice_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not check_func(request, *args, **kwargs):
                return HttpResponseForbidden(error_message)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def parent_can_access_student(request, student_id: int) -> bool:
    """
    Check if parent user can access a specific student's data.
    Returns True if user is parent/guardian of the student or is staff.
    """
    from apps.accounts.models import User
    
    user = request.user
    if not user.is_authenticated:
        return False
    
    # Staff can access all students
    if user.is_staff or user.is_superuser or user.role == User.Role.ADMIN:
        return True
    
    # Parents can only access their own children
    if user.role == User.Role.PARENT:
        from apps.people.models import StudentGuardian
        return StudentGuardian.objects.filter(
            guardian_user=user,
            student_id=student_id,
            can_view_results=True,
        ).exists()
    
    return False


def parent_can_access_invoice(request, invoice_id: int) -> bool:
    """
    Check if parent user can access a specific invoice.
    Parents can only access invoices for their own children.
    """
    from apps.accounts.models import User
    from apps.finance.models import Invoice
    
    user = request.user
    if not user.is_authenticated:
        return False
    
    # Staff/admin can access all invoices
    if user.is_staff or user.is_superuser or user.role == User.Role.ADMIN:
        return True
    
    # Parents can only access invoices for their children
    if user.role == User.Role.PARENT:
        from apps.people.models import StudentGuardian
        try:
            invoice = Invoice.objects.select_related('student').get(id=invoice_id)
            if not invoice.student:
                return False  # Non-student invoices not accessible to parents
            from apps.accounts.permissions import _guardian_finance_qs
            return _guardian_finance_qs(user).filter(student=invoice.student).exists()
        except Invoice.DoesNotExist:
            return False
    
    return False
