"""
Minimal tenant data for portal role smoke crawls (pytest + management command).

Teacher dashboard requires TeacherProfile + active AcademicYear/Term. Finance dashboard
requires an active ComplianceProfile (global first() resolution in finance views).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import RequestFactory
from django.utils import timezone

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.schools.models import School


def resolve_school_from_http_host(host: str):
    """
    Resolve ``School`` the same way tenant middleware does (subdomain, custom domain,
    ``SchoolDomain``). Used by ``crawl_portal_role_urls`` before any crawl or user writes.
    """
    from apps.schools.middleware import _resolve_school_from_request

    stripped = (host or "").strip()
    if not stripped:
        return None
    req = RequestFactory().get("/", HTTP_HOST=stripped)
    return _resolve_school_from_request(req)


def portal_crawl_unresolved_host_message(*, host: str) -> str:
    """Human-readable error when ``--host`` does not map to an active school."""
    import os

    base = os.environ.get("MULTI_TENANT_BASE_DOMAIN", "").strip()
    base_hint = (
        f"\n  MULTI_TENANT_BASE_DOMAIN is {base!r} (subdomain = label before that domain)."
        if base
        else "\n  Set MULTI_TENANT_BASE_DOMAIN so subdomain hosts (e.g. acme.school.edu) resolve."
    )
    return (
        f"Could not resolve an active School for HTTP_HOST={host!r}.{base_hint}\n"
        "  Fix: use a host that matches School.subdomain (or slug), a verified custom_domain, "
        "or a verified SchoolDomain row — same rules as tenant middleware.\n"
        "  The portal role crawl is tenant-only; there is nothing to crawl without a resolved school."
    )


def ensure_portal_smoke_probe_feature_permissions(users_by_role: dict) -> None:
    """
    Grant feature permissions required by ``PORTAL_ROLE_SMOKE_SEEDS`` for synthetic probe users.

    ``accounts:backend_dashboard`` uses ``@permission_required("settings.manage")`` (feature
    permission code), not only ``is_staff``; principals without that code would hit the login
    redirect and fail gate crawls.
    """
    from apps.accounts.models import Permission, User

    perm, _ = Permission.objects.get_or_create(
        code="settings.manage",
        defaults={
            "name": "Manage settings",
            "description": "Probe users for portal/backend smoke crawls.",
        },
    )
    for role in (User.Role.ADMIN, User.Role.PRINCIPAL):
        user = users_by_role.get(role)
        if user is None:
            continue
        if user.has_feature_permission("settings.manage"):
            continue
        user.feature_permissions.add(perm)


def ensure_portal_smoke_prerequisites(*, school: "School", teacher_user: "User | None" = None) -> None:
    from apps.academics.models import AcademicYear, Term
    from apps.finance.models import ComplianceProfile
    from apps.people.models import TeacherProfile

    if not ComplianceProfile.objects.filter(is_active=True).exists():
        ComplianceProfile.objects.create(
            name="Portal smoke compliance",
            country_code="US",
            is_active=True,
        )

    today = timezone.localdate()
    year = AcademicYear.objects.filter(is_active=True, school=school).first()
    if year is None:
        year = AcademicYear.objects.create(
            school=school,
            name="Smoke academic year",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            is_active=True,
        )

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    term = Term.objects.filter(is_active=True, academic_year=year).first()
    if term is None:
        Term.objects.create(
            school=school,
            academic_year=year,
            name="SMOKE1",
            start_date=year.start_date,
            end_date=year.end_date,
            is_active=True,
            position=1,
        )

    if teacher_user is not None:
        profile, _ = TeacherProfile.objects.get_or_create(
            user=teacher_user,
            defaults={"school": school, "is_active": True},
        )
        if profile.school_id != school.id:
            profile.school = school
            profile.is_active = True
            profile.save(update_fields=["school", "is_active"])
