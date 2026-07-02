"""Resolve tenant school on requests where middleware may not have bound ``request.school``."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.accounts.permissions import tenant_operator_hub_eligible

LIFECYCLE_SCHOOL_SESSION_KEY = "rmc_lifecycle_school_id"

_LIFECYCLE_MEMBERSHIP_ROLES = frozenset(
    {
        "ADMIN",
        "PROPRIETOR",
        "IT_ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
    }
)


def bind_lifecycle_school_session(request: HttpRequest, school) -> None:
    """Pin the active tenant for post-signup redirects on the public host."""
    session = getattr(request, "session", None)
    school_id = getattr(school, "pk", None)
    if session is None or school_id is None:
        return
    session[LIFECYCLE_SCHOOL_SESSION_KEY] = str(school_id)
    try:
        session.modified = True
    except AttributeError:
        pass


def _school_from_session(request: HttpRequest, user) -> Any:
    session = getattr(request, "session", None)
    if session is None:
        return None
    school_id = session.get(LIFECYCLE_SCHOOL_SESSION_KEY)
    if not school_id:
        return None
    from apps.schools.models import School
    from apps.schools.tenant_access import user_belongs_to_school

    try:
        school = School.objects.get(pk=school_id)
    except (School.DoesNotExist, TypeError, ValueError):
        return None
    if user is not None and getattr(user, "is_authenticated", False):
        if not getattr(user, "is_superuser", False) and not user_belongs_to_school(
            user, school
        ):
            return None
    return school


def _school_from_signup_verification(user) -> Any:
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return None
    from apps.schools.models import SignupVerification

    # tenant-isolation-allow: pre-tenant-resolution-finds-school-from-signup-verification-by-email
    sv = (
        SignupVerification.objects.filter(email__iexact=email)
        .select_related("school")
        .order_by("-verified_at", "-created_at")
        .first()
    )
    return sv.school if sv else None


def resolve_request_school(request: HttpRequest, *, user=None):
    """``request.school`` when set; else session / signup / membership fallbacks."""
    school = getattr(request, "school", None) or getattr(request, "tenant_school", None)
    if school is not None:
        return school
    user = user or getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    school = _school_from_session(request, user)
    if school is not None:
        return school

    school = _school_from_signup_verification(user)
    if school is not None:
        return school

    from apps.schools.models import SchoolMembership

    # tenant-isolation-allow: pre-tenant-resolution-finds-school-from-user-membership-fallback
    membership = (
        SchoolMembership.objects.filter(user_id=user.pk)
        .select_related("school")
        .order_by("-is_primary", "-id")
        .first()
    )
    return membership.school if membership else None


def can_access_tenant_lifecycle(request: HttpRequest, school) -> bool:
    """Provisioning / fast-path / School Studio for school admins and operator hub users."""
    user = getattr(request, "user", None)
    if school is None or user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or tenant_operator_hub_eligible(user):
        return True
    from apps.schools.models import SchoolMembership
    from apps.accounts.effective_access import school_permission_access
    from apps.schools.tenant_access import user_belongs_to_school

    if not user_belongs_to_school(user, school):
        return False
    if school_permission_access(user, school, "admin"):
        return True
    membership = SchoolMembership.objects.filter(
        user_id=user.pk, school_id=school.pk
    ).first()
    if membership is None:
        return False
    return str(membership.role or "").strip().upper() in _LIFECYCLE_MEMBERSHIP_ROLES


def lifecycle_access_denied_response(request: HttpRequest):
    from django.http import HttpResponseForbidden
    from django.utils.translation import gettext as _

    return HttpResponseForbidden(_("School administrator access required."))


def require_tenant_lifecycle_school(request: HttpRequest):
    """Return ``(school, None)`` or ``(None, forbidden_response)``."""
    school = resolve_request_school(request)
    if school is None or not can_access_tenant_lifecycle(request, school):
        return None, lifecycle_access_denied_response(request)
    return school, None
