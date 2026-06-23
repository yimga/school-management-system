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

    stdout.write(
        style.SUCCESS(
            f"OK — school={school.slug!r} users {pfx}.admin, {pfx}.teacher, "
            f"{pfx}.parent, {pfx}.student password={password!r}"
        )
    )
