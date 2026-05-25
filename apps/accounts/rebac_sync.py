"""Emit relationship tuples from existing membership / guardian / role graphs."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.accounts.rebac import (
    OBJECT_CLASSROOM,
    OBJECT_PERMISSION,
    OBJECT_SCHOOL,
    OBJECT_STUDENT,
    OBJECT_SUBJECT_ASSIGNMENT,
    REL_CAN,
    REL_MEMBER,
    REL_PARENT_OF,
    REL_TEACHER_OF,
    SUBJECT_USER,
    delete_tuples_for_source,
    rebuild_user_permission_tuples,
    write_tuple,
)

logger = logging.getLogger(__name__)

# Membership role → default offline navigation capabilities (read cache only).
ROLE_OFFLINE_CAPABILITIES: dict[str, list[str]] = {
    "TEACHER": [
        "attendance.mark",
        "grade.submit",
        "student.note",
    ],
    "ADMIN": [
        "attendance.mark",
        "grade.submit",
        "settings.manage",
    ],
    "PARENT": [
        "student.note",
    ],
    "BURSAR": [
        "payment.proof_upload",
        "module.finance.read",
    ],
}


def sync_membership_tuples(membership) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    school = membership.school
    user = membership.user
    if not school or not user:
        return
    sid = str(user.pk)
    source_key = f"membership:{membership.pk}"
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.MEMBERSHIP,
        source_key=source_key,
    )
    write_tuple(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
        relation=REL_MEMBER,
        object_type=OBJECT_SCHOOL,
        object_id=str(school.pk),
        source=RelationshipTuple.Source.MEMBERSHIP,
        source_key=source_key,
    )
    role = (membership.role or "").upper()
    for code in ROLE_OFFLINE_CAPABILITIES.get(role, []):
        write_tuple(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
            object_id=code,
            source=RelationshipTuple.Source.MEMBERSHIP,
            source_key=f"{source_key}:cap:{code}",
        )
    rebuild_user_permission_tuples(user, school=school)


def remove_membership_tuples(membership) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    school = membership.school
    if not school:
        return
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.MEMBERSHIP,
        source_key=f"membership:{membership.pk}",
    )


def sync_guardian_tuples(link) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    student = link.student
    user = link.guardian_user
    if not student or not user:
        return
    school = getattr(student, "school", None)
    if school is None:
        return
    sid = str(user.pk)
    source_key = f"guardian:{link.pk}"
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.GUARDIAN,
        source_key=source_key,
    )
    write_tuple(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
        relation=REL_PARENT_OF,
        object_type=OBJECT_STUDENT,
        object_id=str(student.pk),
        source=RelationshipTuple.Source.GUARDIAN,
        source_key=source_key,
    )
    if link.can_view_finance:
        write_tuple(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
            object_id="module.finance.read",
            source=RelationshipTuple.Source.GUARDIAN,
            source_key=f"{source_key}:finance",
        )


def remove_guardian_tuples(link) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    student = link.student
    if not student:
        return
    school = getattr(student, "school", None)
    if school is None:
        return
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.GUARDIAN,
        source_key=f"guardian:{link.pk}",
    )


def sync_teacher_assignment_tuples(assignment) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    if not assignment.is_active:
        remove_teacher_assignment_tuples(assignment)
        return
    teacher = assignment.teacher
    user = getattr(teacher, "user", None)
    school = assignment.school or getattr(teacher, "school", None)
    if not user or not school:
        return
    sid = str(user.pk)
    sa = assignment.subject_assignment
    source_key = f"teacher_assignment:{assignment.pk}"
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.TEACHER_ASSIGNMENT,
        source_key=source_key,
    )
    write_tuple(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
        relation=REL_TEACHER_OF,
        object_type=OBJECT_SUBJECT_ASSIGNMENT,
        object_id=str(sa.pk),
        source=RelationshipTuple.Source.TEACHER_ASSIGNMENT,
        source_key=source_key,
    )
    classroom = getattr(sa, "classroom", None)
    if classroom is not None:
        write_tuple(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_TEACHER_OF,
            object_type=OBJECT_CLASSROOM,
            object_id=str(classroom.pk),
            source=RelationshipTuple.Source.TEACHER_ASSIGNMENT,
            source_key=f"{source_key}:classroom",
        )
    for code in ("grade.submit", "attendance.mark"):
        write_tuple(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
            object_id=code,
            source=RelationshipTuple.Source.TEACHER_ASSIGNMENT,
            source_key=f"{source_key}:{code}",
        )


def remove_teacher_assignment_tuples(assignment) -> None:
    from apps.accounts.models_rebac import RelationshipTuple

    school = assignment.school
    if school is None and assignment.teacher_id:
        school = getattr(assignment.teacher, "school", None)
    if school is None:
        return
    delete_tuples_for_source(
        school=school,
        source=RelationshipTuple.Source.TEACHER_ASSIGNMENT,
        source_key=f"teacher_assignment:{assignment.pk}",
    )


@transaction.atomic
def sync_user_roles_for_school(user, *, school) -> int:
    """Refresh permission tuples after M2M role change."""
    return rebuild_user_permission_tuples(user, school=school)


def backfill_school(school, *, limit_users: int | None = None) -> dict[str, int]:
    """Full tuple rebuild for one tenant (management command)."""
    from apps.accounts.models import User
    from apps.evals.models import TeacherAssignment
    from apps.people.models import StudentGuardian
    from apps.schools.models import SchoolMembership

    stats = {
        "memberships": 0,
        "guardians": 0,
        "teacher_assignments": 0,
        "users": 0,
    }
    for m in SchoolMembership.objects.filter(school=school).select_related("user"):
        sync_membership_tuples(m)
        stats["memberships"] += 1
    for g in StudentGuardian.objects.filter(
        student__school=school,
    ).select_related("guardian_user", "student"):
        sync_guardian_tuples(g)
        stats["guardians"] += 1
    for ta in TeacherAssignment.objects.filter(school=school).select_related(
        "teacher__user",
        "subject_assignment__classroom",
    ):
        sync_teacher_assignment_tuples(ta)
        stats["teacher_assignments"] += 1
    user_ids = SchoolMembership.objects.filter(school=school).values_list(
        "user_id", flat=True,
    )
    qs = User.objects.filter(pk__in=user_ids)
    if limit_users:
        qs = qs[:limit_users]
    for user in qs:
        sync_user_roles_for_school(user, school=school)
        stats["users"] += 1
    return stats
