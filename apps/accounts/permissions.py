"""
Role-based and object-level permission checks for the school management system.

Provides:
- Role hierarchy validation
- Object-level permission decorators
- Permission checking functions for common scenarios
"""

from functools import wraps
from typing import Optional, Callable, Any

from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden, HttpRequest
from django.shortcuts import get_object_or_404

logger = None  # Set after imports to avoid circular deps


# --- Role Hierarchy ---

ROLE_HIERARCHY = {
    "ADMIN": ["ADMIN", "PRINCIPAL", "BURSAR", "TEACHER", "PARENT", "STUDENT"],
    "PRINCIPAL": ["PRINCIPAL", "BURSAR", "TEACHER", "PARENT", "STUDENT"],
    "LEADERSHIP": ["LEADERSHIP", "BURSAR", "TEACHER", "PARENT", "STUDENT"],
    "DEAN": ["DEAN", "TEACHER", "PARENT", "STUDENT"],
    "BURSAR": ["BURSAR", "PARENT"],  # Finance staff
    "HOD": ["HOD", "TEACHER", "STUDENT"],  # Head of department
    "CENSOR": ["CENSOR", "TEACHER", "STUDENT"],  # Academic oversight
    "TEACHER": ["TEACHER", "STUDENT"],  # Classroom level
    "BOARDING_MANAGER": ["BOARDING_MANAGER", "STUDENT"],
    "IT_ADMIN": ["IT_ADMIN"],
    "PARENT": ["PARENT"],
    "STUDENT": ["STUDENT"],
}


def has_role(user, role: str) -> bool:
    """Check if user has a specific role or higher."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role == role or user.roles.filter(code=role).exists()


def has_role_hierarchy(user, required_role: str) -> bool:
    """
    Check if user's role is >= required role in hierarchy.
    
    Example:
        has_role_hierarchy(user, "BURSAR")
        -> True if user is ADMIN or BURSAR (or higher)
        -> False if user is TEACHER
    
    Args:
        user: User instance
        required_role: The minimum role required
        
    Returns:
        True if user has equal or higher privilege
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    user_role = getattr(user, "role", None)
    if not user_role:
        return user.roles.filter(code__in=ROLE_HIERARCHY.get(required_role, [])).exists()
    
    return user_role in ROLE_HIERARCHY.get(required_role, [])


def can_view_student_data(user, student_id: int) -> bool:
    """
    Check if user can view a student's data.
    
    Allowed:
    - ADMIN, PRINCIPAL, DEAN, CENSOR (all students)
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
    
    # Admins and principal can view all
    if has_role_hierarchy(user, "PRINCIPAL"):
        return True
    
    # Get the student
    try:
        student = StudentProfile.objects.get(id=student_id)
    except StudentProfile.DoesNotExist:
        return False
    
    # Teacher can view if student in their classroom
    if has_role(user, "TEACHER"):
        if user.teacher_profile:  # Assumes ForeignKey from User to TeacherProfile
            return student.classroom and student.classroom in user.teacher_profile.classrooms.all()
    
    # Parent can view if this is their child
    if has_role(user, "PARENT"):
        return StudentGuardian.objects.filter(
            guardian=user,
            student=student,
        ).exists()
    
    # Student can only view themselves
    if has_role(user, "STUDENT"):
        return student.user_id == user.id
    
    return False


def can_edit_student_grades(user, student_id: int, subject_id: Optional[int] = None) -> bool:
    """
    Check if user can edit student's grades.
    
    Allowed:
    - ADMIN, PRINCIPAL, DEAN, CENSOR (all subjects)
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
    from apps.academics.models import SubjectAssignment
    
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    
    # Admins can edit all
    if has_role_hierarchy(user, "PRINCIPAL"):
        return True
    
    # Get student
    try:
        student = StudentProfile.objects.get(id=student_id)
    except StudentProfile.DoesNotExist:
        return False
    
    # Teacher: only for their classroom + subject
    if has_role(user, "TEACHER"):
        if not user.teacher_profile:
            return False
        
        # Student in teacher's classroom?
        if student.classroom not in user.teacher_profile.classrooms.all():
            return False
        
        # If subject specified, check assignment
        if subject_id:
            return SubjectAssignment.objects.filter(
                teacher=user.teacher_profile,
                subject_id=subject_id,
                classroom=student.classroom,
            ).exists()
        return True
    
    # HOD: their department
    if has_role(user, "HOD"):
        if not user.hod_profile:  # Assumes ForeignKey
            return False
        return student.classroom.department == user.hod_profile.department
    
    return False


def can_view_invoice(user, invoice_id: int) -> bool:
    """
    Check if user can view an invoice.
    
    Allowed:
    - ADMIN, PRINCIPAL, BURSAR (all invoices)
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
    if has_role_hierarchy(user, "BURSAR"):
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
        return StudentGuardian.objects.filter(
            guardian=user,
            student=invoice.student,
        ).exists()
    
    # Student can view their own invoice
    if has_role(user, "STUDENT"):
        return invoice.student.user_id == user.id
    
    return False


def can_edit_invoice(user, invoice_id: int) -> bool:
    """
    Check if user can edit an invoice (mark as paid, cancel, etc.).
    
    Allowed:
    - ADMIN, PRINCIPAL, BURSAR only
    
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
    
    return has_role_hierarchy(user, "BURSAR")


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
    
    return user_passes_test(check, redirect_url="/authentication/login/")


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
    
    return user_passes_test(check, redirect_url="/authentication/login/")


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
