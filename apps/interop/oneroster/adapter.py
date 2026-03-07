"""
OneRoster 1.1: canonical model to OneRoster JSON (read-only).
Used by apps.api.oneroster_views.
"""

from __future__ import annotations

from typing import Any


def classroom_to_oneroster(classroom: Any, school: Any) -> dict[str, Any]:
    """Map Classroom to OneRoster class object."""
    return {
        "sourcedId": str(classroom.pk),
        "title": classroom.name,
        "classCode": getattr(classroom, "code", "") or "",
        "schoolSourcedId": str(school.pk),
        "status": "active",
    }


def student_to_oneroster(student: Any, school: Any) -> dict[str, Any]:
    """Map StudentProfile to OneRoster user (student) object."""
    return {
        "sourcedId": str(student.pk),
        "username": getattr(student, "student_code", None) or "student-%s" % student.pk,
        "givenName": getattr(student, "first_name", "") or "",
        "familyName": getattr(student, "last_name", "") or "",
        "status": "active" if getattr(student, "is_active", True) else "inactive",
        "classSourcedId": str(student.classroom_id) if getattr(student, "classroom_id", None) else None,
    }


def teacher_to_oneroster(teacher: Any, school: Any) -> dict[str, Any]:
    """Map TeacherProfile to OneRoster user (teacher) object."""
    username = given = family = ""
    if getattr(teacher, "user_id", None) and hasattr(teacher, "user") and teacher.user:
        username = teacher.user.username
        given = getattr(teacher.user, "first_name", "") or ""
        family = getattr(teacher.user, "last_name", "") or ""
    return {
        "sourcedId": str(teacher.pk),
        "username": username or "teacher-%s" % teacher.pk,
        "givenName": given,
        "familyName": family,
        "status": "active" if getattr(teacher, "is_active", True) else "inactive",
    }


def enrollment_to_oneroster(student: Any, school: Any) -> dict[str, Any]:
    """Map StudentProfile (with classroom) to OneRoster enrollment."""
    return {
        "sourcedId": "%s:%s" % (student.pk, student.classroom_id),
        "classSourcedId": str(student.classroom_id),
        "schoolSourcedId": str(school.pk),
        "userSourcedId": str(student.pk),
        "role": "student",
        "status": "active" if getattr(student, "is_active", True) else "inactive",
    }


def build_manifest_resources(school: Any, base_path: str) -> dict[str, str]:
    """Build OneRoster manifest resource URLs for a school."""
    slug = getattr(school, "slug", "") or ""
    return {
        "classes": "%s/classes?school_slug=%s" % (base_path, slug),
        "students": "%s/students?school_slug=%s" % (base_path, slug),
        "teachers": "%s/teachers?school_slug=%s" % (base_path, slug),
        "enrollments": "%s/enrollments?school_slug=%s" % (base_path, slug),
    }
