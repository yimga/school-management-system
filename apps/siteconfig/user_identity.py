"""
Ensure every authenticated user has portal preferences and optional people profiles.

Called on login and at profile/preferences entry points so manager + tenant hosts
never 500 when legacy schema rows or missing preference records exist.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.people.user_profile_access import safe_teacher_profile

logger = logging.getLogger(__name__)

User = get_user_model()

_SCHEMA_ERRORS = (ProgrammingError, DatabaseError, OperationalError)

# Roles that receive a minimal TeacherProfile stub when none exists yet.
_TEACHER_PROFILE_ROLES = frozenset(
    {
        User.Role.TEACHER,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.DEAN,
        User.Role.CENSOR,
        User.Role.HOD,
        User.Role.DEPT_LEAD,
        User.Role.BURSAR,
        User.Role.FINANCE_STAFF,
        User.Role.ACADEMICS_STAFF,
        User.Role.COMMS_STAFF,
        User.Role.SECRETARY,
        User.Role.EXECUTIVE_ASSISTANT,
        User.Role.BOARDING_MANAGER,
        User.Role.ACCOUNTANT,
        User.Role.DISCIPLINE_MASTER,
    }
)


def resolve_school_for_user(user, *, request: Any = None) -> Any:
    """Best-effort school for preference defaults; never raises on schema drift."""
    if request is not None:
        school = getattr(request, "school", None)
        if school is not None:
            return school

    if not user or not getattr(user, "is_authenticated", False):
        return None

    try:
        from apps.schools.models import SchoolMembership

        # tenant-isolation-allow: membership-resolved-by-authenticated-user-primary-key
        membership = (
            SchoolMembership.objects.filter(user=user, is_primary=True)
            .select_related("school")
            .first()
        )
        if membership and membership.school_id:
            return membership.school
        # tenant-isolation-allow: membership-resolved-by-authenticated-user-primary-key
        membership = (
            SchoolMembership.objects.filter(user=user)
            .select_related("school")
            .first()
        )
        if membership and membership.school_id:
            return membership.school
    except _SCHEMA_ERRORS:
        pass

    teacher_profile = safe_teacher_profile(user)
    if teacher_profile and getattr(teacher_profile, "school", None):
        return teacher_profile.school

    try:
        guardian_links = getattr(user, "guardian_links", None)
        if guardian_links is not None:
            link = guardian_links.select_related("student__school").first()
            if link and getattr(link.student, "school", None):
                return link.student.school
    except _SCHEMA_ERRORS:
        pass

    return None


def ensure_user_portal_preferences(user) -> tuple[Any, Any]:
    """Create siteconfig + dashboard preference rows if missing."""
    from apps.siteconfig.models_dashboard import DashboardUserPreference
    from apps.siteconfig.models_tooling import UserPreference

    portal_pref, _ = UserPreference.objects.get_or_create(user=user)
    dash_pref, _ = DashboardUserPreference.objects.get_or_create(user=user)
    # accounts.models.UserPreference — background logo / motion (related_name=preference)
    try:
        from apps.accounts.models import UserPreference as AccountsUserPreference

        AccountsUserPreference.objects.get_or_create(user=user)
    except _SCHEMA_ERRORS:
        logger.debug(
            "ensure_user_portal_preferences: accounts UserPreference skipped (schema)",
            exc_info=True,
        )

    return portal_pref, dash_pref


def ensure_people_profile_for_role(user, *, school: Any = None) -> Any:
    """Ensure a role-appropriate people profile exists when the table is available."""
    role = getattr(user, "role", None)
    if role not in _TEACHER_PROFILE_ROLES:
        return None

    existing = safe_teacher_profile(user)
    if existing is not None:
        return existing

    school = school or resolve_school_for_user(user)
    try:
        from apps.people.models import TeacherProfile

        profile, _created = TeacherProfile.objects.get_or_create(
            user=user,
            defaults={
                "school": school,
                "is_active": True,
                "staff_id": f"STAFF-{user.pk}",
            },
        )
        if school and profile.school_id != school.id:
            profile.school = school
            profile.is_active = True
            profile.save(update_fields=["school", "is_active"])
        return profile
    except _SCHEMA_ERRORS:
        logger.warning(
            "ensure_people_profile_for_role: could not create TeacherProfile for user_id=%s",
            getattr(user, "pk", None),
            exc_info=True,
        )
        return None


def ensure_user_identity(user, *, request: Any = None) -> dict[str, Any]:
    """Full bootstrap: preferences + optional people profile. Safe to call every login."""
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    portal_pref, dash_pref = ensure_user_portal_preferences(user)
    school = resolve_school_for_user(user, request=request)
    people_profile = ensure_people_profile_for_role(user, school=school)

    return {
        "portal_preference": portal_pref,
        "dashboard_preference": dash_pref,
        "school": school,
        "people_profile": people_profile,
    }
