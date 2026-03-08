"""
Role-based and object-level permission checks for the school management system.

Provides:
- Role hierarchy validation
- Object-level permission decorators
- Permission checking functions for common scenarios
"""

from functools import wraps
from typing import Optional, Callable, Any

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.db import DatabaseError, transaction
from django.http import HttpResponseForbidden, HttpRequest
from django.shortcuts import get_object_or_404

logger = None  # Set after imports to avoid circular deps


# --- Role Hierarchy ---

# Higher number = higher privilege.
ROLE_RANK = {
    "SUPERADMIN": 110,
    "ADMIN": 100,
    "LEADERSHIP": 95,
    "PROPRIETOR": 96,
    "PRINCIPAL": 90,
    "VICE_PRINCIPAL": 85,
    "DEAN": 80,
    "HOD": 75,
    "CENSOR": 75,
    "BURSAR": 75,
    "DEPT_LEAD": 74,
    "ACCOUNTANT": 74,
    "DISCIPLINE_MASTER": 73,
    "FINANCE_STAFF": 65,
    "ACADEMICS_STAFF": 65,
    "COMMS_STAFF": 60,
    "IT_ADMIN": 70,
    "BOARDING_MANAGER": 60,
    "TEACHER": 50,
    "PARENT": 20,
    "STUDENT": 10,
}

STUDENT_DATA_GLOBAL_ROLES = {
    "SUPERADMIN",
    "ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "VICE_PRINCIPAL",
    "DEAN",
    "CENSOR",
    "HOD",
    "DEPT_LEAD",
}

GRADE_EDIT_GLOBAL_ROLES = {
    "SUPERADMIN",
    "ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "VICE_PRINCIPAL",
    "DEAN",
    "CENSOR",
    "HOD",
    "DEPT_LEAD",
}

INVOICE_GLOBAL_ROLES = {
    "SUPERADMIN",
    "ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "BURSAR",
    "FINANCE_STAFF",
}

# Module access defaults (read/write). Use feature permissions to override:
# - module.<module>.read
# - module.<module>.write
# - module.<module>.all
ALL_AUTHENTICATED = {"*"}
CONTROL_PLANE_ROLE_CODES = {"SUPERADMIN"}

MODULE_ACCESS_DEFAULTS = {
    # Core portals
    "portal": {
        "read": {"PARENT", "TEACHER", "STUDENT", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "ACADEMICS_STAFF", "COMMS_STAFF", "HOD", "DEPT_LEAD"},
        "write": {"PARENT", "TEACHER", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "ACADEMICS_STAFF", "COMMS_STAFF", "HOD", "DEPT_LEAD"},
    },
    "kb": {
        "read": {"PARENT", "TEACHER", "STUDENT", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "ACADEMICS_STAFF", "COMMS_STAFF"},
        "write": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "COMMS_STAFF"},
    },
    "academics": {
        "read": {"TEACHER", "ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "CENSOR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "CENSOR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
    },
    "people": {
        "read": {"TEACHER", "ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "CENSOR", "BURSAR", "SECRETARY", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "BURSAR", "SECRETARY", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
    },
    "evals": {
        "read": {"TEACHER", "ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "CENSOR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"TEACHER", "ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "CENSOR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
    },
    "reports": {
        "read": {"TEACHER", "PARENT", "STUDENT", "ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "SECRETARY", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"ACADEMICS_STAFF", "HOD", "DEPT_LEAD", "SECRETARY", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
    },
    "finance": {
        "read": {"PARENT", "STUDENT", "FINANCE_STAFF", "BURSAR", "ACCOUNTANT", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"FINANCE_STAFF", "BURSAR", "ACCOUNTANT", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL"},
    },
    "analytics": {
        "read": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "ACADEMICS_STAFF"},
        "write": {"ADMIN", "SUPERADMIN"},
    },
    "payroll": {
        "read": {"FINANCE_STAFF", "BURSAR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL"},
        "write": {"FINANCE_STAFF", "BURSAR", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL"},
    },
    "compliance": {
        "read": {"ADMIN", "SUPERADMIN", "IT_ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
    },
    "siteconfig": {
        "read": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
        "write": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
    },
    "accounts": {
        "read": ALL_AUTHENTICATED,
        "write": ALL_AUTHENTICATED,
    },
    "communication": {
        "read": {"TEACHER", "PARENT", "ADMIN", "SUPERADMIN", "COMMS_STAFF", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
        "write": {"TEACHER", "PARENT", "ADMIN", "SUPERADMIN", "COMMS_STAFF", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"},
    },
    "requests": {
        "read": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "HOD", "DEPT_LEAD", "BURSAR", "FINANCE_STAFF", "ACADEMICS_STAFF", "COMMS_STAFF", "IT_ADMIN"},
        "write": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "HOD", "DEPT_LEAD", "BURSAR", "FINANCE_STAFF", "ACADEMICS_STAFF", "COMMS_STAFF", "IT_ADMIN"},
    },
    "emis": {
        "read": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "ACADEMICS_STAFF"},
        "write": {"ADMIN", "SUPERADMIN", "IT_ADMIN", "ACADEMICS_STAFF"},
    },
    "observability": {
        "read": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
        "write": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
    },
    "discipline": {
        "read": {"ADMIN", "SUPERADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "DISCIPLINE_MASTER", "CENSOR"},
        "write": {"DISCIPLINE_MASTER", "CENSOR", "ADMIN", "SUPERADMIN"},
    },
    "accounting": {
        "read": {"ACCOUNTANT", "ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR"},
        "write": {"ACCOUNTANT", "ADMIN", "SUPERADMIN"},
    },
    "stock": {
        "read": {"ACCOUNTANT", "ADMIN", "SUPERADMIN"},
        "write": {"ACCOUNTANT", "ADMIN", "SUPERADMIN"},
    },
    # API is guarded by endpoint-level permissions; allow all authenticated users.
    "api": {
        "read": ALL_AUTHENTICATED,
        "write": ALL_AUTHENTICATED,
    },
    "api_center": {
        "read": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
        "write": {"ADMIN", "SUPERADMIN", "IT_ADMIN"},
    },
}


def _strip_control_plane_roles(role_codes: set[str]) -> set[str]:
    if role_codes == ALL_AUTHENTICATED:
        return role_codes
    return {code for code in role_codes if code not in CONTROL_PLANE_ROLE_CODES}


STUDENT_DATA_GLOBAL_ROLES = _strip_control_plane_roles(STUDENT_DATA_GLOBAL_ROLES)
GRADE_EDIT_GLOBAL_ROLES = _strip_control_plane_roles(GRADE_EDIT_GLOBAL_ROLES)
INVOICE_GLOBAL_ROLES = _strip_control_plane_roles(INVOICE_GLOBAL_ROLES)

for _module_permissions in MODULE_ACCESS_DEFAULTS.values():
    for _action, _roles in list(_module_permissions.items()):
        _module_permissions[_action] = _strip_control_plane_roles(_roles)

# Group permissions by module for RBAC UI (grouped display; additive only, do not remove).
PERMISSION_GROUPS = {
    "Discipline": ["discipline.manage"],
    "Accounting": ["accounting.view", "accounting.manage"],
    "Stock": ["stock.view", "stock.manage"],
    "Strategic": ["strategic.report"],
    "Exam registration": ["exam_registration.manage"],
    "Attendance": ["attendance.view", "attendance.manage"],
    "Cahier de Texte": ["cahier.verify"],
    "Finance": ["finance.view", "finance.manage"],
    "Reports": ["reports.manage"],
    "Settings": ["settings.manage"],
    "Portal": ["portal.manage"],
    "Communication": ["communication.manage"],
    "Student": ["student.manage"],
    "Data": ["data.access"],
    "API Center": ["api_center.manage"],
}

# Role categories for RBAC UI (grouped display; additive only, do not remove).
ROLE_CATEGORIES = {
    "Leadership": ["ADMIN", "SUPERADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL", "VICE_PRINCIPAL"],
    "Academic": ["DEAN", "CENSOR", "HOD", "DEPT_LEAD", "ACADEMICS_STAFF"],
    "Finance": ["BURSAR", "FINANCE_STAFF", "ACCOUNTANT"],
    "Support": ["SECRETARY", "EXECUTIVE_ASSISTANT", "VIRTUAL_ASSISTANT", "IT_ADMIN"],
    "Disciplinary": ["DISCIPLINE_MASTER"],
    "Other": ["TEACHER", "BOARDING_MANAGER", "PARENT", "STUDENT"],
}


def _user_has_role(user, role: str) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == role:
        return True
    if user.roles.filter(code=role).exists():
        return True
    from django.utils import timezone
    from apps.accounts.models import TemporaryRoleGrant
    from django.db.models import Q
    now = timezone.now()
    return TemporaryRoleGrant.objects.filter(
        user=user, role__code=role, expires_at__gt=now
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).exists()


def _user_has_any_role(user, roles: set[str]) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if roles == ALL_AUTHENTICATED:
        return True
    user_role = getattr(user, "role", None)
    if user_role in roles:
        return True
    if user.roles.filter(code__in=roles).exists():
        return True
    from django.utils import timezone
    from apps.accounts.models import TemporaryRoleGrant
    from django.db.models import Q
    now = timezone.now()
    return TemporaryRoleGrant.objects.filter(
        user=user, role__code__in=roles, expires_at__gt=now
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).exists()


def api_user_has_any_role(user, roles: set[str] | tuple[str, ...]) -> bool:
    """
    Safe for API/DRF: use from permission classes. Handles unauthenticated and
    checks both user.role and user.roles (AccessRole). Use for consistent RBAC.
    """
    if not user:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role_set = set(roles) if not isinstance(roles, set) else roles
    if role_set == ALL_AUTHENTICATED:
        return True
    user_role = (getattr(user, "role", None) or "").strip().upper()
    if user_role in role_set:
        return True
    try:
        if user.roles.filter(code__in=role_set).exists():
            return True
        from django.utils import timezone
        from apps.accounts.models import TemporaryRoleGrant
        from django.db.models import Q
        now = timezone.now()
        return TemporaryRoleGrant.objects.filter(
            user=user, role__code__in=role_set, expires_at__gt=now
        ).filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now)
        ).exists()
    except Exception:
        return False


def can_access_module(user, module: str, action: str = "read") -> bool:
    """
    Module-level access guard for role + feature-permission enforcement.
    Feature permissions override role defaults:
      - module.<module>.read
      - module.<module>.write
      - module.<module>.all
    Unknown modules are denied by default (fail-closed); log for audit.
    """
    import logging
    _logger = logging.getLogger(__name__)

    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True

    module = (module or "").strip().lower()
    action = "write" if action == "write" else "read"

    if module == "admin":
        return getattr(user, "is_staff", False)

    # Explicit allow list: unknown modules are denied (default-deny)
    if module not in MODULE_ACCESS_DEFAULTS:
        _logger.warning("Module access check for unknown module %r (action=%s) -> denied", module, action)
        return False

    if user.has_feature_permission(f"module.{module}.all"):
        return True
    if action == "write" and user.has_feature_permission(f"module.{module}.write"):
        return True
    if action == "read" and user.has_feature_permission(f"module.{module}.read"):
        return True

    defaults = MODULE_ACCESS_DEFAULTS[module]
    allowed = defaults.get(action, defaults.get("read", set()))
    return _user_has_any_role(user, allowed)


def _guardian_finance_qs(user):
    """
    Return guardian links filtered by site flag that can require explicit finance opt-in.
    When the flag is disabled (default), any guardian relationship is considered sufficient
    for finance visibility; when enabled, guardians must have can_view_finance=True.
    On DB/settings errors we fail closed: require opt-in (narrower access).
    """
    import logging
    from apps.people.models import StudentGuardian
    _logger = logging.getLogger(__name__)
    try:
        from apps.platform_runtime.helpers import get_effective_flags_for_school
        with transaction.atomic():
            school = (
                StudentGuardian.objects.filter(guardian_user=user)
                .values_list("student__school", flat=True)
                .first()
            )
            flags = get_effective_flags_for_school(school) or {}
            require_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    except DatabaseError:
        _logger.warning("SiteSettings unavailable for guardian finance opt-in; failing closed (require_opt_in=True).")
        require_opt_in = True
    except Exception:
        _logger.warning("SiteSettings error for guardian finance opt-in; failing closed (require_opt_in=True).")
        require_opt_in = True

    filters = {"guardian_user": user}
    if require_opt_in:
        filters["can_view_finance"] = True
    return StudentGuardian.objects.filter(**filters)


def guardian_finance_student_ids(user):
    """Helper to return student IDs a guardian can see for finance purposes."""
    return _guardian_finance_qs(user).values_list("student_id", flat=True)

def _role_rank(role: str | None) -> int:
    if not role:
        return 0
    return ROLE_RANK.get(role, 0)


def has_role(user, role: str) -> bool:
    """Check if user has a specific role (including via temporary grant)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _user_has_role(user, role)


def has_role_hierarchy(user, required_role: str) -> bool:
    """
    Check if user's role rank is >= required role rank.

    AccessRole codes only grant the exact role requested (no implicit hierarchy).
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    user_role = getattr(user, "role", None)
    if _role_rank(user_role) >= _role_rank(required_role):
        return True

    return _user_has_role(user, required_role)


def can_view_student_data(user, student_id: int) -> bool:
    """
    Check if user can view a student's data.
    
    Allowed:
    - ADMIN, LEADERSHIP, PRINCIPAL, VICE_PRINCIPAL, DEAN, CENSOR (all students)
    - TEACHER (students in their classroom)
    - PARENT (their own children)
    - STUDENT (themselves only)
    
    Args:
        user: User instance
        student_id: StudentProfile ID to check
        
    Returns:
        True if authorized
    """
    from apps.people.models import StudentProfile, StudentGuardian
    
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    # Global view roles
    if any(has_role(user, role) for role in STUDENT_DATA_GLOBAL_ROLES):
        return True
    
    # Get the student
    try:
        student = StudentProfile.objects.get(id=student_id)
    except StudentProfile.DoesNotExist:
        return False
    
    # Teacher can view if student in their classroom
    if has_role(user, "TEACHER"):
        teacher = getattr(user, "teacher_profile", None)
        if teacher and student.classroom_id:
            from apps.evals.models import TeacherAssignment
            return TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=student.classroom_id,
            ).exists()
    
    # Parent can view if this is their child
    if has_role(user, "PARENT"):
        return StudentGuardian.objects.filter(
            guardian_user=user,
            student=student,
            can_view_results=True,
        ).exists()
    
    # Student can only view themselves
    if has_role(user, "STUDENT"):
        student_user_id = getattr(student, "user_id", None)
        return student_user_id == user.id
    
    return False


def can_edit_student_grades(user, student_id: int, subject_id: Optional[int] = None) -> bool:
    """
    Check if user can edit student's grades.
    
    Allowed:
    - ADMIN, LEADERSHIP, PRINCIPAL, VICE_PRINCIPAL, DEAN, CENSOR (all subjects)
    - TEACHER (only their assigned subjects for students in classroom)
    - HOD (their department)
    
    Args:
        user: User instance
        student_id: StudentProfile ID
        subject_id: Optional Subject ID for fine-grained check
        
    Returns:
        True if authorized
    """
    from apps.people.models import StudentProfile
    from apps.evals.models import TeacherAssignment
    
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    # Global edit roles
    if any(has_role(user, role) for role in GRADE_EDIT_GLOBAL_ROLES):
        return True
    
    # Get student
    try:
        student = StudentProfile.objects.get(id=student_id)
    except StudentProfile.DoesNotExist:
        return False
    
    # Teacher: only for their classroom + subject
    if has_role(user, "TEACHER"):
        teacher = getattr(user, "teacher_profile", None)
        if not teacher:
            return False
        assignment_filter = TeacherAssignment.objects.filter(
            teacher=teacher,
            is_active=True,
            subject_assignment__classroom=student.classroom,
        )

        if subject_id:
            assignment_filter = assignment_filter.filter(subject_assignment__subject_id=subject_id)

        return assignment_filter.exists()
    
    # HOD: their department
    if has_role(user, "HOD"):
        hod_profile = getattr(user, "hod_profile", None)
        if not hod_profile:
            return False
        return student.classroom.department_id == hod_profile.department_id
    
    return False


def can_view_invoice(user, invoice_id: int) -> bool:
    """
    Check if user can view an invoice.
    
    Allowed:
    - ADMIN, LEADERSHIP, PRINCIPAL, BURSAR (all invoices)
    - PARENT (invoices for their children)
    - STUDENT (invoices for themselves)
    
    Args:
        user: User instance
        invoice_id: Invoice ID
        
    Returns:
        True if authorized
    """
    from apps.finance.models import Invoice
    from apps.people.models import StudentGuardian
    
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    # Finance staff can view all
    if any(has_role(user, role) for role in INVOICE_GLOBAL_ROLES):
        return True
    
    # Get invoice
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        return False
    
    if not invoice.student:
        return False
    
    # Parent can view their child's invoice
    if has_role(user, "PARENT"):
        return _guardian_finance_qs(user).filter(student=invoice.student).exists()
    
    # Student can view their own invoice
    if has_role(user, "STUDENT"):
        student_user_id = getattr(invoice.student, "user_id", None)
        return student_user_id == user.id
    
    return False


def can_edit_invoice(user, invoice_id: int) -> bool:
    """
    Check if user can edit an invoice (mark as paid, cancel, etc.).
    
    Allowed:
    - ADMIN, LEADERSHIP, PRINCIPAL, BURSAR only
    
    Args:
        user: User instance
        invoice_id: Invoice ID
        
    Returns:
        True if authorized
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    return any(has_role(user, role) for role in INVOICE_GLOBAL_ROLES)


# --- Decorators ---

def finance_access_required(*roles: str):
    """
    Decorator requiring specific finance roles.
    
    Usage:
        @finance_access_required("BURSAR", "ADMIN")
        def finance_dashboard(request):
            ...
    """
    def check(user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        user_role = getattr(user, "role", None)
        return user_role in roles or user.roles.filter(code__in=roles).exists()
    
    return user_passes_test(check, redirect_url=settings.LOGIN_URL)


def evaluation_access_required(can_edit: bool = False):
    """
    Decorator for grade/evaluation access.
    
    Args:
        can_edit: If True, require edit permission (TEACHER+). If False, allow viewers.
    
    Usage:
        @evaluation_access_required(can_edit=False)
        def view_grades(request, student_id):
            ...
        
        @evaluation_access_required(can_edit=True)
        def edit_grades(request, student_id):
            ...
    """
    if can_edit:
        allowed_roles = ["ADMIN", "PRINCIPAL", "DEAN", "TEACHER", "HOD", "CENSOR"]
    else:
        allowed_roles = [
            "ADMIN", "PRINCIPAL", "DEAN", "TEACHER", "HOD",
            "CENSOR", "PARENT", "STUDENT",
        ]
    
    def check(user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        user_role = getattr(user, "role", None)
        return user_role in allowed_roles or user.roles.filter(
            code__in=allowed_roles
        ).exists()
    
    return user_passes_test(check, redirect_url=settings.LOGIN_URL)


def object_permission_required(permission_func: Callable[[Any, int], bool]):
    """
    Higher-order decorator for object-level permission checks.
    
    Usage:
        @object_permission_required(can_view_student_data)
        def student_detail(request, student_id):
            ...
    
    The permission_func should accept (user, object_id) and return bool.
    The view should have object_id as the first path argument.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            # Extract object ID from args or kwargs
            object_id = args[0] if args else kwargs.get("pk") or kwargs.get("id") or kwargs.get("student_id")
            
            if not object_id:
                return HttpResponseForbidden("Invalid request")
            
            if not permission_func(request.user, int(object_id)):
                return HttpResponseForbidden(
                    "You don't have permission to access this resource."
                )
            
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


# Shortcut decorators

def invoice_access_required(view_func):
    """Decorator for invoice views requiring permission check."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        invoice_id = args[0] if args else kwargs.get("pk") or kwargs.get("invoice_id")
        
        if not invoice_id:
            return HttpResponseForbidden("Invalid request")
        
        if not can_view_invoice(request.user, int(invoice_id)):
            return HttpResponseForbidden(
                "You don't have permission to view this invoice."
            )
        
        return view_func(request, *args, **kwargs)
    return _wrapped


def student_detail_access_required(view_func):
    """Decorator for student detail views requiring permission check."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        student_id = args[0] if args else kwargs.get("pk") or kwargs.get("student_id")
        
        if not student_id:
            return HttpResponseForbidden("Invalid request")
        
        if not can_view_student_data(request.user, int(student_id)):
            return HttpResponseForbidden(
                "You don't have permission to view this student's data."
            )
        
        return view_func(request, *args, **kwargs)
    return _wrapped
