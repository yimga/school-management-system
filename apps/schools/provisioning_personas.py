"""
Optional post-provision sample users + student record for instant operational UI.

Disabled by default. Enable via provision kwarg ``seed_demo_personas=True`` (super create-school API)
or env ``RMC_PROVISION_SEED_DEMO_PERSONAS=1`` (staging).
"""

from __future__ import annotations

import logging
import os
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


def should_seed_demo_personas(**kwargs) -> bool:
    if kwargs.get("seed_demo_personas"):
        return True
    return (
        os.getenv("RMC_PROVISION_SEED_DEMO_PERSONAS", "").strip().lower()
        in ("1", "true", "yes", "on")
    )


def seed_sample_teacher_parent_student(school) -> dict:
    """
    Idempotent-ish: one teacher, one parent, one student in first classroom (when present).
    Passwords are random (returned only in provision payload / logs — avoid logging raw passwords in production).
    """
    from apps.academics.models import AcademicYear, Classroom
    from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
    from apps.schools.models import SchoolMembership, SchoolProvisioningEvent

    year = (
        AcademicYear.objects.filter(school=school, is_active=True).first()
        or AcademicYear.objects.filter(school=school).order_by("-id").first()
    )
    if not year:
        return {"ok": False, "error": "no_academic_year"}

    room = (
        Classroom.objects.filter(school=school, academic_year=year)
        .order_by("id")
        .first()
    )

    sid = str(school.pk).replace("-", "")[:10]
    pfx = f"ob{sid}"[:32]
    password = secrets.token_urlsafe(14)

    created_users: list[str] = []

    with transaction.atomic():
        for username, role, is_staff in (
            (f"{pfx}.teacher", User.Role.TEACHER, True),
            (f"{pfx}.parent", User.Role.PARENT, False),
        ):
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@sample.runmycampus.local",
                    "role": role,
                    "is_staff": is_staff,
                    "is_active": True,
                },
            )
            if not created:
                u.role = role
                u.is_staff = is_staff
                u.is_active = True
                u.email = u.email or f"{username}@sample.runmycampus.local"
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
            created_users.append(username)

        student, _ = StudentProfile.objects.get_or_create(
            student_code=f"SAMPLE-{sid}",
            defaults={
                "school": school,
                "academic_year": year,
                "first_name": "Sample",
                "last_name": "Student",
                "status": StudentProfile.Status.RETURNING,
                "classroom": room,
            },
        )
        fields_to_update = []
        if student.academic_year_id != year.id:
            student.academic_year = year
            fields_to_update.append("academic_year")
        if room and student.classroom_id != room.id:
            student.classroom = room
            fields_to_update.append("classroom")
        if fields_to_update:
            student.save(update_fields=fields_to_update)

        parent = User.objects.filter(username=f"{pfx}.parent").first()
        if parent:
            StudentGuardian.objects.get_or_create(
                guardian_user=parent,
                student=student,
                defaults={"relationship": StudentGuardian.Relationship.GUARDIAN},
            )

    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.SAMPLE_DATA_READY,
        status=SchoolProvisioningEvent.Status.SUCCESS,
        message="Sample teacher, parent, and student records created for instant UI.",
        payload={
            "usernames": created_users,
            "student_code": student.student_code,
            "classroom_id": str(room.id) if room else "",
            "password_rotated": True,
            "hint": "Sample accounts share one rotated password; change or disable in production.",
        },
    )
    return {
        "ok": True,
        "usernames": created_users,
        "student_code": student.student_code,
        "password": password,
    }
