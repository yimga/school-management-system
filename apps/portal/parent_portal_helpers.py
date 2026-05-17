"""
Phase F: Parent/student portal helpers — active child switcher and privacy.

- active_child_id: stored in session; use get_active_child_id() / set_active_child().
- require_parent_child_access(request, child_id): use in any view that takes child_id;
  returns (student, None) if allowed, or (None, HttpResponse) if forbidden.
- RTL: set in template context from school.default_region (e.g. is_rtl) for parent portal.
"""

from django.http import HttpResponseForbidden

SESSION_KEY_ACTIVE_CHILD = "portal_active_child_id"


def get_active_child_id(request):
    """Return the currently selected child ID for parent dashboard (from session), or None."""
    return request.session.get(SESSION_KEY_ACTIVE_CHILD)


def set_active_child(request, child_id):
    """
    Set the active child for this parent session. Caller must verify the user
    is a guardian for the given child_id (e.g. via require_parent_child_access).
    """
    request.session[SESSION_KEY_ACTIVE_CHILD] = child_id
    request.session.modified = True


def get_guardian_child_ids(request):
    """Return set of student IDs the current user is linked to as guardian."""
    from .services import guardian_student_links

    links = guardian_student_links(request.user, results_only=True)
    return {link.student_id for link in links}


def require_parent_child_access(request, child_id):
    """
    Ensure the request user is a guardian for the given child_id. Use in any
    parent-portal view that accepts child_id (query or path).

    Returns:
        (student, None) if allowed; (None, HttpResponse) if forbidden (403).
    """
    from apps.people.models import StudentProfile

    allowed_ids = get_guardian_child_ids(request)
    if child_id is None or int(child_id) not in allowed_ids:
        return None, HttpResponseForbidden("You do not have access to this student.")
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        student = StudentProfile.objects.get(pk=int(child_id))
    except (ValueError, StudentProfile.DoesNotExist):
        return None, HttpResponseForbidden("Student not found.")
    return student, None
