"""
OneRoster 1.1: canonical model to OneRoster JSON (read-only).
Used by apps.api.oneroster_views.
"""

from __future__ import annotations

from typing import Any


def classroom_to_oneroster(classroom: Any, school: Any) -> dict[str, Any]:
    """Map Classroom to OneRoster class object."""
    out = {
        "sourcedId": str(classroom.pk),
        "title": classroom.name,
        "classCode": getattr(classroom, "code", "") or "",
        "schoolSourcedId": str(school.pk),
        "status": "active",
    }
    u = getattr(classroom, "updated_at", None)
    if u is not None:
        try:
            out["dateLastModified"] = u.isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return out


def student_to_oneroster(student: Any, school: Any) -> dict[str, Any]:
    """Map StudentProfile to OneRoster user (student) object."""
    return {
        "sourcedId": str(student.pk),
        "username": getattr(student, "student_code", None) or "student-%s" % student.pk,
        "givenName": getattr(student, "first_name", "") or "",
        "familyName": getattr(student, "last_name", "") or "",
        "status": "active" if getattr(student, "is_active", True) else "inactive",
        "classSourcedId": str(student.classroom_id)
        if getattr(student, "classroom_id", None)
        else None,
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


def term_to_academic_session(term: Any, school: Any) -> dict[str, Any]:
    """Map Term to OneRoster academicSession."""
    title = (getattr(term, "custom_label", None) or "").strip() or str(
        getattr(term, "name", "") or "Term"
    )
    return {
        "sourcedId": str(term.pk),
        "title": title,
        "startDate": str(getattr(term, "start_date", "")),
        "endDate": str(getattr(term, "end_date", "")),
        "schoolSourcedId": str(school.pk),
        "status": "active",
    }


def build_manifest_resources(school: Any, base_path: str) -> dict[str, str]:
    """Build OneRoster manifest resource URLs for a school."""
    slug = getattr(school, "slug", "") or ""
    return {
        "academicSessions": "%s/academicSessions?school_slug=%s" % (base_path, slug),
        "classes": "%s/classes?school_slug=%s" % (base_path, slug),
        "students": "%s/students?school_slug=%s" % (base_path, slug),
        "teachers": "%s/teachers?school_slug=%s" % (base_path, slug),
        "enrollments": "%s/enrollments?school_slug=%s" % (base_path, slug),
        "orgs": "%s/orgs?school_slug=%s" % (base_path, slug),
        "courses": "%s/courses?school_slug=%s" % (base_path, slug),
        "users": "%s/users?school_slug=%s" % (base_path, slug),
    }


def school_to_oneroster_org(school: Any) -> dict[str, Any]:
    return {
        "sourcedId": "org:%s" % school.pk,
        "name": getattr(school, "name", "") or "School",
        "type": "school",
        "identifier": getattr(school, "slug", "") or str(school.pk),
    }


def department_to_oneroster_org(dept: Any, school: Any) -> dict[str, Any]:
    return {
        "sourcedId": "dept:%s" % dept.pk,
        "name": getattr(dept, "name", "") or "Department",
        "type": "department",
        "parentSourcedId": "org:%s" % school.pk,
    }


def subject_to_oneroster_course(subject: Any, school: Any) -> dict[str, Any]:
    return {
        "sourcedId": "course:%s" % subject.pk,
        "title": getattr(subject, "name", "") or "Course",
        "courseCode": getattr(subject, "code", "") or "",
        "schoolSourcedId": str(school.pk),
        "status": "active",
    }


def student_to_oneroster_user(
    student: Any, school: Any, profile: str = "standard"
) -> dict[str, Any]:
    base = student_to_oneroster(student, school)
    base["role"] = "student"
    base["orgSourcedIds"] = ["org:%s" % school.pk]
    if profile == "minimal":
        return {
            "sourcedId": base["sourcedId"],
            "role": "student",
            "status": base.get("status"),
            "givenName": base.get("givenName", ""),
            "familyName": base.get("familyName", ""),
        }
    if profile == "full":
        base["metadata"] = {"student_code": getattr(student, "student_code", "") or ""}
    return base


def teacher_to_oneroster_user(
    teacher: Any, school: Any, profile: str = "standard"
) -> dict[str, Any]:
    base = teacher_to_oneroster(teacher, school)
    base["role"] = "teacher"
    base["orgSourcedIds"] = ["org:%s" % school.pk]
    if profile == "minimal":
        return {
            "sourcedId": base["sourcedId"],
            "role": "teacher",
            "status": base.get("status"),
            "givenName": base.get("givenName", ""),
            "familyName": base.get("familyName", ""),
        }
    if profile == "full":
        u = getattr(teacher, "user", None)
        base["email"] = getattr(u, "email", "") if u else ""
    return base


SYNTHETIC_STUDENTS = [
    ("Demo", "StudentA", "SYN-001"),
    ("Demo", "StudentB", "SYN-002"),
    ("Demo", "StudentC", "SYN-003"),
]


def synthetic_oneroster_rows(school: Any) -> dict[str, list[dict[str, Any]]]:
    """Partner-certification / sandbox roster (no PII)."""
    sid = str(school.pk)
    classes = [
        {
            "sourcedId": "syn-class-1",
            "title": "Synthetic Class 1",
            "classCode": "SYN-C1",
            "schoolSourcedId": sid,
            "status": "active",
        }
    ]
    users = []
    for i, (g, f, code) in enumerate(SYNTHETIC_STUDENTS, start=1):
        users.append(
            {
                "sourcedId": "syn-stu-%s" % i,
                "username": code,
                "givenName": g,
                "familyName": f,
                "role": "student",
                "status": "active",
                "classSourcedId": "syn-class-1",
                "orgSourcedIds": ["org:%s" % sid],
            }
        )
    users.append(
        {
            "sourcedId": "syn-tch-1",
            "username": "syn.teacher",
            "givenName": "Synthetic",
            "familyName": "Teacher",
            "role": "teacher",
            "status": "active",
            "orgSourcedIds": ["org:%s" % sid],
        }
    )
    enr = [
        {
            "sourcedId": "syn-stu-%s:syn-class-1" % i,
            "classSourcedId": "syn-class-1",
            "schoolSourcedId": sid,
            "userSourcedId": "syn-stu-%s" % i,
            "role": "student",
            "status": "active",
        }
        for i in range(1, 4)
    ]
    return {
        "orgs": [school_to_oneroster_org(school)],
        "classes": classes,
        "users": users,
        "enrollments": enr,
        "academicSessions": [
            {
                "sourcedId": "syn-term-1",
                "title": "Synthetic Term",
                "startDate": "2025-09-01",
                "endDate": "2026-06-30",
                "schoolSourcedId": sid,
                "status": "active",
            }
        ],
        "courses": [
            {
                "sourcedId": "syn-course-1",
                "title": "Synthetic Subject",
                "courseCode": "SYN-101",
                "schoolSourcedId": sid,
                "status": "active",
            }
        ],
    }
