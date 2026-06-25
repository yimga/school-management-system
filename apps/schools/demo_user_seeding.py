"""
Shared demo user seeding for tenant sandboxes (RunMyCampus-neutral usernames).

Used by ``seed_demo_tenant_users``.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership


def resolve_demo_school(
    *,
    school_slug: str,
    extra_filter: Q | None = None,
) -> School | None:
    """
    Resolve target school: explicit slug wins; else optional extra_filter;
    else first active school by created_at.
    """
    slug_filter = (school_slug or "").strip()
    if slug_filter:
        return School.objects.filter(slug=slug_filter, is_active=True).first()
    if extra_filter is not None:
        return School.objects.filter(extra_filter, is_active=True).first()
    return School.objects.filter(is_active=True).order_by("created_at").first()


_PORTAL_TOGGLE_KEYS = (
    "enable_student_portal",
    "enable_parent_portal",
    "enable_teacher_portal",
)


def _ensure_demo_portal_toggles_enabled() -> None:
    """Platform defaults: parent/teacher/student demo personas need portals on."""
    try:
        from apps.platform_runtime.models import RuntimeDefaults
        from apps.siteconfig.config_service import invalidate_effective_site_settings_cache

        rt, _ = RuntimeDefaults.objects.get_or_create(pk=1, defaults={"payload": {}})
        update_fields: list[str] = []
        for key in _PORTAL_TOGGLE_KEYS:
            if getattr(rt, key, None) is not True:
                setattr(rt, key, True)
                update_fields.append(key)
        payload = dict(rt.payload or {})
        payload_dirty = False
        for key in _PORTAL_TOGGLE_KEYS:
            if payload.get(key) is False:
                payload[key] = True
                payload_dirty = True
        if payload_dirty:
            rt.payload = payload
            update_fields.append("payload")
        if update_fields:
            update_fields.append("updated_at")
            rt.save(update_fields=list(dict.fromkeys(update_fields)))
            invalidate_effective_site_settings_cache()
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass


def _ensure_demo_active_term(school: School, year: AcademicYear) -> None:
    """Teacher marks list requires active year + term (batch 1728 P0 E2E)."""
    try:
        from apps.academics.models import Term

        if Term.objects.filter(school=school, academic_year=year, is_active=True).exists():
            return
        Term.objects.get_or_create(
            school=school,
            academic_year=year,
            name="FIRST",
            defaults={
                "custom_label": "Term 1",
                "position": 1,
                "start_date": year.start_date,
                "end_date": year.end_date,
                "is_active": True,
            },
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        pass


def _ensure_demo_finance_profile(school: School) -> None:
    """Money Center dashboard requires an active ComplianceProfile (batch 1728 P0 E2E)."""
    try:
        from apps.finance.models import ComplianceProfile
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        cc = (getattr(school, "country_code", None) or "US").strip().upper()[:2] or "US"
        profile, created = ComplianceProfile.objects.get_or_create(
            name=f"Demo finance — {school.slug}",
            country_code=cc,
            defaults={"is_active": True},
        )
        if not profile.is_active:
            profile.is_active = True
            profile.save(update_fields=["is_active"])
        site = get_platform_site_settings_record(create=True)
        if getattr(site, "compliance_profile_id", None) != profile.pk:
            site.apply_feature_control_state(
                field_updates={"compliance_profile_id": profile.pk},
            )
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass


def _ensure_demo_admin_backend_access(user: User) -> None:
    """Backend dashboard requires settings.manage (batch 1726 role-home E2E)."""
    if user.role != User.Role.ADMIN:
        return
    try:
        from apps.accounts.models import Permission

        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user.feature_permissions.add(perm)
    except (AttributeError, ImportError, TypeError, ValueError):
        pass


def _ensure_demo_user_login_ready(user: User) -> None:
    """E2E/sandbox: skip quarterly review nag and minimum-strength traps."""
    from django.utils import timezone

    update_fields: list[str] = []
    if getattr(user, "requires_password_change", False):
        user.requires_password_change = False
        update_fields.append("requires_password_change")
    score = getattr(user, "password_strength_score", None)
    if score is None or int(score) < 80:
        user.password_strength_score = 100
        update_fields.append("password_strength_score")
    user.last_security_posture_review_at = timezone.now()
    update_fields.append("last_security_posture_review_at")
    if update_fields:
        user.save(update_fields=update_fields)

    try:
        from allauth.account.models import EmailAddress

        email = (getattr(user, "email", None) or "").strip()
        if email:
            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={"verified": True, "primary": True},
            )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass


def _ensure_school_demo_portal_toggles_enabled(school: School) -> None:
    """Per-tenant overrides in school.settings must not block demo portal E2E."""
    try:
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default
        from apps.siteconfig.config_service import invalidate_effective_site_settings_cache

        changed = False
        for key in _PORTAL_TOGGLE_KEYS:
            if set_runtime_default(school=school, field=key, value=True):
                changed = True

        settings = getattr(school, "settings", None) or {}
        if not isinstance(settings, dict):
            settings = {}
        top_dirty = False
        for key in _PORTAL_TOGGLE_KEYS:
            if settings.get(key) is False:
                settings[key] = True
                top_dirty = True
        if top_dirty:
            school.settings = settings
            school.save(update_fields=["settings"])
            changed = True

        if changed:
            invalidate_effective_site_settings_cache()
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass


def seed_demo_users_for_school(
    school: School,
    *,
    password: str,
    username_prefix: str,
    stdout: Any,
    style: Any,
) -> None:
    """Create demo admin, teacher, parent, student with StudentGuardian link."""
    year = (
        AcademicYear.objects.filter(school=school, is_active=True).first()
        or AcademicYear.objects.filter(school=school).order_by("-id").first()
    )
    if not year:
        from datetime import date

        year = AcademicYear.objects.create(
            school=school,
            name=f"{date.today().year}-{date.today().year + 1}",
            start_date=date(date.today().year, 9, 1),
            end_date=date(date.today().year + 1, 8, 31),
            is_active=True,
        )
        stdout.write(style.WARNING(f"Created academic year: {year.name}"))

    _ensure_demo_active_term(school, year)
    _ensure_demo_finance_profile(school)

    pfx = (username_prefix or "demo").strip().lower().replace(" ", "")
    specs = [
        (f"{pfx}.admin", User.Role.ADMIN, True),
        (f"{pfx}.teacher", User.Role.TEACHER, True),
        (f"{pfx}.parent", User.Role.PARENT, False),
        (f"{pfx}.student", User.Role.STUDENT, False),
    ]

    with transaction.atomic():
        for username, role, is_staff in specs:
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@demo.runmycampus.local",
                    "role": role,
                    "is_staff": is_staff,
                    "is_active": True,
                },
            )
            if not created:
                u.role = role
                u.is_staff = is_staff
                u.is_active = True
                u.email = u.email or f"{username}@demo.runmycampus.local"
                u.save(update_fields=["role", "is_staff", "is_active", "email"])
            u.set_password(password)
            u.save(update_fields=["password"])
            _ensure_demo_user_login_ready(u)
            if role == User.Role.ADMIN:
                _ensure_demo_admin_backend_access(u)

            SchoolMembership.objects.update_or_create(
                user=u,
                school=school,
                defaults={"role": role, "is_primary": True},
            )

            if role == User.Role.TEACHER:
                TeacherProfile.objects.update_or_create(
                    user=u,
                    defaults={"school": school, "is_active": True},
                )

        parent = User.objects.get(username=f"{pfx}.parent")
        sid = str(school.pk).replace("-", "")[:10]
        student, _ = StudentProfile.objects.get_or_create(
            student_code=f"DEMO-{sid}",
            defaults={
                "school": school,
                "academic_year": year,
                "first_name": "Demo",
                "last_name": "Student",
                "status": StudentProfile.Status.RETURNING,
            },
        )
        if student.academic_year_id != year.id:
            student.academic_year = year
            student.save(update_fields=["academic_year"])
        student_user = User.objects.get(username=f"{pfx}.student")
        if student.user_id != student_user.id:
            student.user = student_user
            student.save(update_fields=["user"])
        StudentGuardian.objects.get_or_create(
            guardian_user=parent,
            student=student,
            defaults={"relationship": StudentGuardian.Relationship.GUARDIAN},
        )

    _ensure_demo_portal_toggles_enabled()
    _ensure_school_demo_portal_toggles_enabled(school)

    stdout.write(
        style.SUCCESS(
            f"OK - school={school.slug!r} users {pfx}.admin, {pfx}.teacher, "
            f"{pfx}.parent, {pfx}.student password={password!r}"
        )
    )
