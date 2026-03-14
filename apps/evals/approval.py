from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable, List
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.academics.models import AcademicYear, Term, SubjectAssignment
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.siteconfig.models import default_grade_approval_roles, default_grade_post_roles
from apps.people.models import StudentProfile, TeacherProfile

from .models import GradeApprovalRequest, AssessmentWeights
from .notifications import NotificationService

SCORE_FIELDS = ["seq1", "seq2", "exam", "mock", "practical"]
FINAL_STATUSES = {GradeApprovalRequest.Status.APPROVED, GradeApprovalRequest.Status.REJECTED}


def _normalize_roles(raw_roles: Iterable[str]) -> list[str]:
    return [str(role).upper().strip() for role in (raw_roles or []) if role]


def get_grade_approval_policy(school=None, policy=None):
    """Phase 1: Single read path for grade approval config. Use policy when provided/school set else SiteSettings.
    Prefer policy from request.tenant_runtime.policy when in request context."""
    if policy is not None and isinstance(policy, dict):
        ga = policy.get("grade_approval")
        if isinstance(ga, dict) and ga:
            return ga
    if school is not None:
        try:
            from apps.policies.policy_registry import get_effective_policy
            out = get_effective_policy(school)
            ga = out.get("grade_approval")
            if isinstance(ga, dict) and ga:
                return ga
        except Exception:
            pass
    try:
        site = get_effective_site_settings(school=school)
        return {
            "grade_post_roles": getattr(site, "grade_post_roles", None) or default_grade_post_roles(),
            "grade_approval_roles": getattr(site, "grade_approval_roles", None) or default_grade_approval_roles(),
            "grade_approval_deadline_days": max(1, getattr(site, "grade_approval_deadline_days", 3) or 3),
            "grade_approval_deadline_note": (getattr(site, "grade_approval_deadline_note", None) or "").strip(),
            "grade_approval_auto_validate": getattr(site, "grade_approval_auto_validate", True),
            "grade_approval_enabled": getattr(site, "grade_approval_enabled", False),
        }
    except Exception:
        return {
            "grade_post_roles": default_grade_post_roles(),
            "grade_approval_roles": default_grade_approval_roles(),
            "grade_approval_deadline_days": 3,
            "grade_approval_deadline_note": "",
            "grade_approval_auto_validate": True,
            "grade_approval_enabled": False,
        }


def grade_post_roles(school=None, policy=None) -> list[str]:
    policy = get_grade_approval_policy(school=school, policy=policy)
    return _normalize_roles(policy.get("grade_post_roles") or [])


def grade_post_users(school=None, policy=None) -> Iterable[User]:
    roles = grade_post_roles(school=school, policy=policy)
    if not roles:
        return User.objects.filter(is_superuser=True)
    base_q = Q(role__in=roles) | Q(roles__code__in=roles)
    return User.objects.filter(base_q).distinct()


def user_has_any_role(user: User, roles: list[str]) -> bool:
    if not user or not roles:
        return False
    if user.is_superuser:
        return True
    role_upper = get_user_role(user)
    if role_upper in roles:
        return True
    return user.roles.filter(code__in=roles).exists()


def user_can_finalize_submission(user: User, school=None, policy=None) -> bool:
    return user_has_any_role(user, grade_post_roles(school=school, policy=policy))


def _collect_validation_flags(
    entries: List[dict],
    academic_year: AcademicYear,
    term: Term,
    classroom,
) -> list[dict]:
    if not entries:
        return []

    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=classroom,
        term=term,
    )
    required = []
    if weights.seq1_weight > 0:
        required.append("seq1")
    if weights.seq2_weight > 0:
        required.append("seq2")
    if weights.exam_weight > 0:
        required.append("exam")
    if weights.mock_weight > 0:
        required.append("mock")
    if weights.practical_weight > 0:
        required.append("practical")

    missing_required = 0
    score_issues = False
    max_score = weights.score_scale or 20
    for entry in entries:
        for field in required:
            if entry["scores"].get(field) is None:
                missing_required += 1
        for field, value in entry["scores"].items():
            if value is None:
                continue
            if value < 0 or value > max_score:
                score_issues = True

    flags = []
    if missing_required:
        flags.append(
            {
                "code": "missing_required_fields",
                "message": f"{missing_required} required component(s) missing",
            }
        )
    if score_issues:
        flags.append(
            {
                "code": "score_out_of_range",
                "message": f"Scores found outside 0-{max_score}",
            }
        )
    return flags


def _parse_score(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return parsed


def grade_entries_from_submission(students: Iterable[StudentProfile], post_data) -> List[dict]:
    entries = []
    for student in students:
        scores = {}
        has_score = False
        for field in SCORE_FIELDS:
            parsed = _parse_score(post_data.get(f"{field}_{student.id}"))
            scores[field] = parsed
            if parsed is not None:
                has_score = True
        remarks = (post_data.get(f"remarks_{student.id}") or "").strip()
        if remarks:
            has_score = True
        entries.append({
            "student_id": student.id,
            "student_code": student.student_code,
            "student_name": f"{student.last_name} {student.first_name}",
            "scores": scores,
            "remarks": remarks,
            "has_scores": has_score,
        })
    return entries


def _serialize_entry(entry: dict) -> dict:
    return {
        "student_id": entry["student_id"],
        "student_code": entry["student_code"],
        "student_name": entry["student_name"],
        "scores": {
            field: str(entry["scores"].get(field)) if entry["scores"].get(field) is not None else None
            for field in SCORE_FIELDS
        },
        "remarks": entry.get("remarks", ""),
        "has_scores": entry.get("has_scores", False),
    }


def _build_summary(total_students: int, submitted_rows: int) -> dict:
    return {
        "total_students": total_students,
        "submitted_rows": submitted_rows,
    }


def grade_approver_roles(school=None, policy=None) -> list[str]:
    policy = get_grade_approval_policy(school=school, policy=policy)
    roles = policy.get("grade_approval_roles") or []
    if roles:
        return [str(r).upper() for r in roles]
    return [str(role).upper() for role in default_grade_approval_roles()]


def grade_approver_users(school=None, policy=None) -> Iterable[User]:
    roles = grade_approver_roles(school=school, policy=policy)
    if not roles:
        return User.objects.filter(is_superuser=True)
    base_q = Q(role__in=roles) | Q(roles__code__in=roles)
    return User.objects.filter(base_q).distinct()


def create_grade_approval_request(
    *,
    teacher: TeacherProfile,
    subject_assignment: SubjectAssignment,
    academic_year: AcademicYear,
    term: Term,
    entries: List[dict],
    requested_by,
) -> GradeApprovalRequest:
    trimmed = [entry for entry in entries if entry.get("has_scores")]
    if not trimmed:
        raise ValueError("Cannot request approval for empty submission.")
    serialized = [_serialize_entry(entry) for entry in trimmed]
    summary = _build_summary(total_students=len(entries), submitted_rows=len(trimmed))
    school = getattr(teacher, "school", None) or (getattr(subject_assignment, "classroom", None) and getattr(subject_assignment.classroom, "school", None))
    policy = get_grade_approval_policy(school)
    deadline_days = max(1, policy.get("grade_approval_deadline_days", 3))
    timezone.now() + timedelta(days=deadline_days)
    if policy.get("grade_approval_auto_validate", True):
        _collect_validation_flags(
            trimmed,
            academic_year=academic_year,
            term=term,
            classroom=getattr(subject_assignment, "classroom", None),
        )
    with transaction.atomic():
        request_obj = GradeApprovalRequest.objects.create(
            teacher=teacher,
            subject_assignment=subject_assignment,
            academic_year=academic_year,
            term=term,
            entries=serialized,
            summary=summary,
            requested_by=requested_by,
        )
    _notify_grade_approvers(request_obj)
    return request_obj


def _notify_grade_approvers(request_obj: GradeApprovalRequest) -> None:
    school = getattr(getattr(request_obj, "teacher", None), "school", None) or (
        getattr(getattr(request_obj, "subject_assignment", None), "classroom", None)
        and getattr(getattr(request_obj.subject_assignment, "classroom", None), "school", None)
    )
    approvers = list(grade_approver_users(school=school))
    if not approvers:
        return
    service = NotificationService()
    for approver in approvers:
        if not approver.email:
            continue
        service.send_grade_approval_request_email(approver, request_obj)
