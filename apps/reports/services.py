from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import DatabaseError
from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist

from apps.global_registries.models import EducationSystemProfile, RegionConfig
from apps.platform_runtime.helpers import get_effective_site_settings, get_platform_defaults
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.policies.policy_registry import get_effective_policy

from apps.academics.models import Term
from apps.evals.models import AssessmentWeights, Evaluation
from apps.evals.services import classroom_term_rankings, school_term_rankings
from apps.people.models import StudentProfile
from apps.reports.models import PromotionRule, TermPublishStatus


def _approved_or_unrequested_subject_assignment_filter(
    academic_year_id: int,
    term_id: int,
    classroom_ids: Optional[Iterable[int]] = None,
):
    """
    When reports_use_approved_grades_only is True: return (approved_sa_ids, any_request_sa_ids).
    Include Evaluation if subject_assignment_id in approved_sa_ids OR subject_assignment_id not in any_request_sa_ids.
    """
    from apps.evals.models import GradeApprovalRequest
    latest_status_by_sa = _latest_grade_approval_status_by_subject_assignment(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom_ids=classroom_ids,
    )
    approved_ids = {
        sa_id
        for sa_id, status in latest_status_by_sa.items()
        if status == GradeApprovalRequest.Status.APPROVED
    }
    any_request_ids = set(latest_status_by_sa.keys())
    return approved_ids, any_request_ids


def _site_settings_for_school(school=None):
    return get_effective_site_settings(school=school)


def _normalize_classroom_scope(
    classroom_ids: Optional[Iterable[int]],
) -> Optional[set[int]]:
    if classroom_ids is None:
        return None
    normalized: set[int] = set()
    for classroom_id in classroom_ids:
        try:
            normalized.add(int(classroom_id))
        except (TypeError, ValueError):
            continue
    return normalized


def _latest_grade_approval_status_by_subject_assignment(
    academic_year_id: int,
    term_id: int,
    classroom_ids: Optional[Iterable[int]] = None,
) -> dict[int, str]:
    """
    Return latest GradeApprovalRequest status per subject assignment for one year/term.
    """
    from apps.evals.models import GradeApprovalRequest

    latest_status_by_sa: dict[int, str] = {}
    classroom_scope = _normalize_classroom_scope(classroom_ids)
    approvals = GradeApprovalRequest.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
    )
    if classroom_scope is not None:
        approvals = approvals.filter(subject_assignment__classroom_id__in=classroom_scope)
    rows = (
        approvals
        .order_by("subject_assignment_id", "-requested_at", "-id")
        .values_list("subject_assignment_id", "status")
    )
    for sa_id, status in rows:
        if sa_id not in latest_status_by_sa:
            latest_status_by_sa[sa_id] = status
    return latest_status_by_sa


def grade_approval_publish_readiness(
    academic_year_id: int,
    term_id: int,
    classroom_ids: Optional[Iterable[int]] = None,
) -> dict[str, int | bool]:
    """
    Evaluate whether a term is ready for publishing under approval governance rules.
    Only subject assignments that already have evaluations are considered.
    """
    from apps.evals.models import GradeApprovalRequest

    classroom_scope = _normalize_classroom_scope(classroom_ids)
    evaluations = Evaluation.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
    )
    if classroom_scope is not None:
        evaluations = evaluations.filter(subject_assignment__classroom_id__in=classroom_scope)
    evaluated_subject_assignment_ids = set(
        evaluations.values_list("subject_assignment_id", flat=True).distinct()
    )
    latest_status_by_sa = _latest_grade_approval_status_by_subject_assignment(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom_ids=classroom_scope,
    )

    pending_statuses = {
        GradeApprovalRequest.Status.PENDING,
        GradeApprovalRequest.Status.UNDER_REVIEW,
        GradeApprovalRequest.Status.REVISION_REQUESTED,
    }
    pending_ids = {
        sa_id
        for sa_id, status in latest_status_by_sa.items()
        if status in pending_statuses
    } & evaluated_subject_assignment_ids
    rejected_ids = {
        sa_id
        for sa_id, status in latest_status_by_sa.items()
        if status == GradeApprovalRequest.Status.REJECTED
    } & evaluated_subject_assignment_ids
    approved_ids = {
        sa_id
        for sa_id, status in latest_status_by_sa.items()
        if status == GradeApprovalRequest.Status.APPROVED
    } & evaluated_subject_assignment_ids
    missing_ids = evaluated_subject_assignment_ids - set(latest_status_by_sa.keys())

    return {
        "subject_assignments_with_grades": len(evaluated_subject_assignment_ids),
        "approved_count": len(approved_ids),
        "pending_count": len(pending_ids),
        "rejected_count": len(rejected_ids),
        "missing_count": len(missing_ids),
        "ready_for_publish": not pending_ids and not rejected_ids and not missing_ids,
    }

def is_term_published(academic_year_id: int, term_id: int, classroom_id: int) -> bool:
    """
    Published if either:
    - whole-school publish exists, OR
    - class-level publish exists
    """
    school_pub = TermPublishStatus.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom__isnull=True,
        is_published=True,
    ).exists()

    class_pub = TermPublishStatus.objects.filter(
        academic_year_id=academic_year_id,
        term_id=term_id,
        classroom_id=classroom_id,
        is_published=True,
    ).exists()

    return school_pub or class_pub


def _promotion_rule_for_student(student: StudentProfile, academic_year) -> Optional[PromotionRule]:
    rule = PromotionRule.objects.filter(
        academic_year=academic_year,
        classroom=student.classroom,
    ).first()
    if rule:
        return rule
    return PromotionRule.objects.filter(academic_year=academic_year, classroom__isnull=True).first()


def _annual_subject_averages(student: StudentProfile, academic_year) -> list[tuple]:
    """
    Return list of (subject, category, annual_average) for the student in this year.
    Used for technical (ITC/ATC) promotion rule: 5 subjects, 2 Professional + 1 Related.
    """
    from django.db.models import Q
    from apps.academics.models import Subject
    terms = terms_for_student(academic_year, student.classroom)
    if not terms:
        return []
    site = _site_settings_for_school(getattr(student, "school", None))
    use_approved_only = getattr(site, "reports_use_approved_grades_only", False)
    acc = {}  # subject_id -> {"subject": Subject, "category": str, "scores": [float]}
    for term in terms:
        evals_qs = Evaluation.objects.filter(
            student=student,
            term=term,
            academic_year=academic_year,
        ).select_related("subject_assignment", "subject_assignment__subject")
        if use_approved_only:
            approved_ids, any_request_ids = _approved_or_unrequested_subject_assignment_filter(
                academic_year.id, term.id
            )
            evals_qs = evals_qs.filter(
                Q(subject_assignment_id__in=approved_ids) | ~Q(subject_assignment_id__in=any_request_ids)
            )
        for e in evals_qs:
            if not e.subject_assignment or not e.subject_assignment.subject_id:
                continue
            subj = e.subject_assignment.subject
            category = getattr(subj, "category", None) or Subject.Category.OTHER
            sid = subj.id
            if sid not in acc:
                acc[sid] = {"subject": subj, "category": category, "scores": []}
            acc[sid]["scores"].append(float(e.total_score))
    result = []
    for data in acc.values():
        scores = data["scores"]
        avg = sum(scores) / len(scores) if scores else 0.0
        result.append((data["subject"], data["category"], avg))
    return result


def get_promotion_status(student, academic_year, overall_average):
    if overall_average is None:
        return "NO_DATA"

    rule = _promotion_rule_for_student(student, academic_year)
    if not rule:
        return "PENDING"

    avg = float(overall_average)
    threshold = float(rule.promotion_average)

    if getattr(rule, "use_technical_promotion_rule", False):
        subject_avgs = _annual_subject_averages(student, academic_year)
        pass_count = 0
        professional_passed = 0
        related_passed = 0
        from apps.academics.models import Subject
        for subj, category, subj_avg in subject_avgs:
            if subj_avg >= threshold:
                pass_count += 1
                if category == Subject.Category.PROFESSIONAL:
                    professional_passed += 1
                elif category in (Subject.Category.RELATED, Subject.Category.GENERAL):
                    related_passed += 1
        if avg >= threshold and pass_count >= 5 and professional_passed >= 2 and related_passed >= 1:
            return "PROMOTED"
        if avg < float(rule.demotion_average):
            return "DEMOTED"
        return "REPEAT"

    if avg >= threshold:
        return "PROMOTED"
    if avg < float(rule.demotion_average):
        return "DEMOTED"
    return "REPEAT"


def get_promotion_thresholds(student: StudentProfile, academic_year) -> Optional[dict]:
    rule = _promotion_rule_for_student(student, academic_year)
    if not rule:
        return None
    return {
        "promotion_average": float(rule.promotion_average),
        "demotion_average": float(rule.demotion_average),
    }


def terms_for_student(academic_year, classroom) -> list[Term]:
    terms = list(Term.objects.filter(academic_year=academic_year).order_by("start_date", "name"))
    if not classroom.allows_third_term:
        terms = [t for t in terms if getattr(t, "position", None) != 3]
    return terms


def student_has_financial_clearance(student: StudentProfile, academic_year) -> bool:
    """
    True if the school does not block report downloads by debt, or if the student
    has no outstanding balance for this academic year. Used to block term/annual
    report download when block_report_download_if_outstanding_balance is True.
    """
    site = _site_settings_for_school(getattr(student, "school", None))
    if callable(getattr(site, "get_backend_feature_flags", None)):
        flags = site.get_backend_feature_flags()
    else:
        flags = getattr(site, "backend_feature_flags", None) or {}
    if not flags.get("block_report_download_if_outstanding_balance", True):
        return True
    from apps.finance.models import Invoice
    from decimal import Decimal
    invoices = Invoice.objects.filter(
        student=student,
        academic_year=academic_year,
    ).exclude(status=Invoice.Status.VOID)
    for inv in invoices:
        if inv.computed_balance > Decimal("0.00"):
            return False
    return True


def student_has_outstanding_returns(student: StudentProfile, academic_year) -> bool:
    """
    True if the student has unreturned resources for this academic year.
    Used to block report download when block_report_download_if_outstanding_returns is True.
    """
    site = _site_settings_for_school(getattr(student, "school", None))
    if callable(getattr(site, "get_backend_feature_flags", None)):
        flags = site.get_backend_feature_flags()
    else:
        flags = getattr(site, "backend_feature_flags", None) or {}
    if not flags.get("block_report_download_if_outstanding_returns", False):
        return False
    from apps.people.models import StudentResourceReturn
    return StudentResourceReturn.objects.filter(
        student=student,
        academic_year=academic_year,
        returned_at__isnull=True,
    ).exists()


def notify_parent_report_blocked_by_debt(student: StudentProfile, academic_year, *, dedupe_hours: int = 24) -> bool:
    """
    Send SMS to a guardian when report download is blocked due to outstanding fees.
    Deduplication: at most one SMS per (student, year) per dedupe_hours (default 24).
    Returns True if SMS was sent, False if skipped (no phone, already sent, or send failed).
    """
    from django.core.cache import cache
    from apps.people.models import StudentGuardian
    from apps.siteconfig.cache_utils import get_tenant_cache_prefix

    school_id = getattr(student, "school_id", None)
    prefix = f"school:{school_id}" if school_id else get_tenant_cache_prefix()
    cache_key = f"{prefix}:report_block_sms:{student.id}:{getattr(academic_year, 'id', academic_year)}"
    if cache.get(cache_key):
        return False
    guardians = StudentGuardian.objects.filter(student=student).select_related("guardian_user")
    phone = None
    for g in guardians:
        phone = getattr(g, "phone", None) or (g.guardian_user and getattr(g.guardian_user, "phone", None))
        if phone and str(phone).strip():
            break
    if not phone:
        return False
    try:
        from apps.evals.notifications import NotificationService
        notifier = NotificationService()
        student_name = getattr(student, "get_full_name", lambda: f"{student.last_name} {student.first_name}")()
        year_name = getattr(academic_year, "name", str(academic_year))
        message = (
            f"Report card for {student_name} is not available until fees are cleared for {year_name}. "
            "Please visit the Bursary."
        )
        sent = notifier.send_sms(str(phone).strip(), message)
        if sent:
            cache.set(cache_key, "1", timeout=dedupe_hours * 3600)
        return sent
    except (OSError, ConnectionError, AttributeError, TypeError, ValueError, KeyError):
        log_exception_with_context(
            "reports.services: notify_parent_report_blocked_by_debt failed to send report-blocked SMS to parent",
            school_id=school_id,
            extra={
                "student_id": getattr(student, "id", None),
                "academic_year_id": getattr(academic_year, "id", None),
            },
        )
        return False


def are_terms_published(academic_year_id: int, term_ids: Iterable[int], classroom_id: int) -> bool:
    for term_id in term_ids:
        if not is_term_published(academic_year_id, term_id, classroom_id):
            return False
    return True


def _rank_position(rankings, student_id: int) -> Optional[int]:
    for idx, agg in enumerate(rankings, start=1):
        if getattr(agg.student, "id", None) == student_id:
            return idx
    return None


CAMEROON_REPORT_LABELS = {
    "student": "Student / Eleve",
    "classroom": "Class / Classe",
    "term": "Term / Trimestre",
    "average": "Average / Moyenne",
    "class_rank": "Class Rank / Rang Classe",
    "specialty_rank": "Specialty Rank / Rang Specialite",
    "school_rank": "School Rank / Rang Etablissement",
    "promotion": "Promotion / Decision",
    "teacher_remark": "Teacher Remark / Appreciation",
    "sequence_1": "Sequence 1 / Sequence 1",
    "sequence_2": "Sequence 2 / Sequence 2",
    "exam": "Exam / Examen",
    "mock": "Mock / Probatoire",
    "practical": "Practical / Pratique",
    "total": "Total / Total",
}


GLOBAL_REPORT_LABELS = {
    "student": "Student",
    "classroom": "Class",
    "term": "Term",
    "average": "Average",
    "class_rank": "Class Rank",
    "specialty_rank": "Group Rank",
    "school_rank": "School Rank",
    "promotion": "Promotion Decision",
    "teacher_remark": "Teacher Remark",
    "sequence_1": "Assessment 1",
    "sequence_2": "Assessment 2",
    "exam": "Exam",
    "mock": "Mock",
    "practical": "Practical",
    "total": "Total",
}


def _profile_report_labels_for_school(school) -> dict:
    if not school:
        return {}
    policy = get_effective_policy(school)
    profile_code = str(policy.get("education_profile_code") or "").strip()
    profile = None
    if profile_code:
        profile = (
            EducationSystemProfile.objects.filter(code=profile_code, is_active=True)
            .only("config")
            .first()
        )
    if profile is None:
        profile = EducationSystemProfile.for_school(school)
    profile_config = dict(getattr(profile, "config", None) or {})
    profile_labels = profile_config.get("report_labels")
    if not isinstance(profile_labels, dict):
        return {}
    return {str(key): str(value) for key, value in profile_labels.items() if value is not None}


def resolve_report_labels(
    student: Optional[StudentProfile] = None,
    school=None,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Resolve report labels with deterministic precedence:
    global defaults -> region defaults -> profile overrides -> school overrides.
    When policy is provided (e.g. request.tenant_runtime.policy), use it instead of resolving from school.
    """
    labels = dict(GLOBAL_REPORT_LABELS)

    if school is None and student is not None:
        school = getattr(student, "school", None)

    # No country/region branching: use profile (region-derived) and policy only (Section 24.2).
    labels.update(_profile_report_labels_for_school(school))

    if policy is None and school is not None:
        policy = get_effective_policy(school)
    if policy is None:
        policy = {}
    custom_labels = policy.get("report_labels")
    if isinstance(custom_labels, dict):
        labels.update({str(key): str(value) for key, value in custom_labels.items() if value is not None})

    return labels


def _resolve_report_labels(student: StudentProfile) -> dict:
    return resolve_report_labels(student=student)


def _rank_display(position: Optional[int], size: int) -> str:
    pos = position if position is not None else "-"
    total = size if size else "-"
    return f"{pos} / {total}"


def _subject_rankings_for_student(student: StudentProfile, academic_year, term: Term, subject_assignment_ids: list[int]) -> dict[int, str]:
    if not subject_assignment_ids:
        return {}

    evaluations = (
        Evaluation.objects.filter(
            academic_year=academic_year,
            term=term,
            subject_assignment_id__in=subject_assignment_ids,
            student__classroom=student.classroom,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("subject_assignment_id", "student__last_name", "student__first_name")
    )

    grouped: dict[int, list[Evaluation]] = {}
    for evaluation in evaluations:
        grouped.setdefault(evaluation.subject_assignment_id, []).append(evaluation)

    ranking_map: dict[int, str] = {}
    for subject_assignment_id, rows in grouped.items():
        eligible = [row for row in rows if row.is_complete_for_ranking]
        if not eligible:
            ranking_map[subject_assignment_id] = _rank_display(None, 0)
            continue
        ranked = sorted(eligible, key=lambda row: float(row.total_score), reverse=True)
        position = None
        for index, ranked_row in enumerate(ranked, start=1):
            if ranked_row.student_id == student.id:
                position = index
                break
        ranking_map[subject_assignment_id] = _rank_display(position, len(ranked))
    return ranking_map


def _sequence_weight_cues(weights, labels: dict) -> list[dict]:
    fields = [
        ("seq1", labels.get("sequence_1", GLOBAL_REPORT_LABELS["sequence_1"]), getattr(weights, "seq1_weight", 0)),
        ("seq2", labels.get("sequence_2", GLOBAL_REPORT_LABELS["sequence_2"]), getattr(weights, "seq2_weight", 0)),
        ("exam", labels.get("exam", GLOBAL_REPORT_LABELS["exam"]), getattr(weights, "exam_weight", 0)),
        ("mock", labels.get("mock", GLOBAL_REPORT_LABELS["mock"]), getattr(weights, "mock_weight", 0)),
        ("practical", labels.get("practical", GLOBAL_REPORT_LABELS["practical"]), getattr(weights, "practical_weight", 0)),
    ]
    cues = []
    for key, label, weight in fields:
        if not weight:
            continue
        cues.append({"key": key, "label": label, "weight": int(weight)})
    return cues


def _auto_teacher_remark(average: Optional[float]) -> str:
    if average is None:
        return "Pending results."
    if average >= 16:
        return "Excellent performance."
    if average >= 14:
        return "Very good work."
    if average >= 12:
        return "Good progress."
    if average >= 10:
        return "Satisfactory performance."
    if average >= 8:
        return "Needs improvement."
    return "Unsatisfactory performance."


def _school_report_metadata(school=None) -> dict:
    site = _site_settings_for_school(school)
    return {
        "school_name": site.site_name,
        "school_code": site.school_code,
        "country": site.country,
        "region": site.region,
        "ministry": site.ministry,
        "tagline": site.tagline,
    }


def _region_display_context(
    school=None,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Return display settings for report templates (date_format, currency, grading_scale, etc.).
    When school is set, use policy (get_effective_policy) and tenant locale only; no direct region branching.
    When policy is provided (e.g. request.tenant_runtime.policy), use it instead of resolving from school.
    """
    from apps.siteconfig.currency import get_currency_symbol
    if policy is None and school is not None:
        policy = get_effective_policy(school)
    if policy is None:
        policy = {}
    try:
        region_code = getattr(settings, "REGION_CODE", "") or get_platform_defaults(use_db=False)["region_code"]
        region = RegionConfig.objects.get(code=region_code)
    except (ObjectDoesNotExist, DatabaseError, KeyError, TypeError, AttributeError, ValueError):
        log_exception_with_context(
            "reports.services: _region_display_context region lookup failed, using default",
            school_id=getattr(school, "id", None) if school else None,
            extra={"context": "_region_display_context_region"},
        )
        region = RegionConfig.get_default()
    _pd = get_platform_defaults(use_db=False)
    cur_code = getattr(region, "default_currency", None) or _pd["currency"]
    date_fmt = getattr(region, "date_format", "DD/MM/YYYY")
    grading_scale = (policy.get("grading") or {}).get("grading_scale") or getattr(region, "grading_scale", None) or _pd["grading_scale"]
    decimal_sep = getattr(region, "decimal_separator", ".")
    thousands_sep = getattr(region, "thousands_separator", ",")
    report_template_family = None
    if school:
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale, get_report_template_family_for_school
            locale = get_tenant_locale(school=school)
            if locale.get("date_format"):
                date_fmt = locale["date_format"]
            if locale.get("currency"):
                cur_code = locale["currency"]
            if locale.get("grading_scale"):
                grading_scale = locale["grading_scale"]
            report_template_family = get_report_template_family_for_school(school)
        except (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError):
            log_exception_with_context(
                "reports.services: _region_display_context tenant locale/template_family failed",
                school_id=getattr(school, "id", None),
                extra={"context": "_region_display_context_tenant_locale"},
            )
    return {
        "region": region,
        "date_format": date_fmt,
        "currency_symbol": get_currency_symbol(cur_code),
        "decimal_separator": decimal_sep,
        "thousands_separator": thousands_sep,
        "grading_scale": grading_scale,
        "report_template_family": report_template_family,
    }


def term_report_context(student: StudentProfile, academic_year, term: Term) -> dict:
    from django.db.models import Q
    qs = Evaluation.objects.filter(student=student, term=term, academic_year=academic_year)
    school = getattr(student, "school", None)
    site = _site_settings_for_school(school)
    if getattr(site, "reports_use_approved_grades_only", False):
        approved_ids, any_request_ids = _approved_or_unrequested_subject_assignment_filter(
            academic_year.id, term.id
        )
        # Include evaluations whose subject has been approved or has no approval request
        qs = qs.filter(
            Q(subject_assignment_id__in=approved_ids) | ~Q(subject_assignment_id__in=any_request_ids)
        )
    evaluations = list(qs.select_related(
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "teacher__user",
    ).order_by("subject_assignment__subject__name"))

    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=student.classroom,
        term=term,
    )
    labels = _resolve_report_labels(student)

    rows = []
    total_weighted = 0.0
    total_coef = 0.0
    subject_rankings = _subject_rankings_for_student(
        student=student,
        academic_year=academic_year,
        term=term,
        subject_assignment_ids=[evaluation.subject_assignment_id for evaluation in evaluations],
    )

    for e in evaluations:
        coef = float(e.subject_assignment.coefficient or 1)
        average_score = float(e.total_score)
        total_score = average_score * coef
        teacher_name = ""
        if getattr(e, "teacher", None):
            teacher_name = e.teacher.user.get_full_name() or e.teacher.user.username
        rows.append({
            "subject": e.subject_assignment.subject.name,
            "coef": coef,
            "seq1": e.seq1_score if e.seq1_score is not None else e.test1,
            "seq2": e.seq2_score if e.seq2_score is not None else e.test2,
            "exam": e.exam_score,
            "mock": e.mock_score,
            "practical": e.practical_score,
            "average": average_score,
            "total": total_score,
            "subject_rank_display": subject_rankings.get(e.subject_assignment_id, "- / -"),
            "teacher_name": teacher_name,
            "remark": e.remarks,
            "complete": e.is_complete_for_ranking,
        })
        total_weighted += average_score * coef
        total_coef += coef

    overall_average = (total_weighted / total_coef) if total_coef else None

    class_rankings = classroom_term_rankings(student.classroom, term)
    school_rankings = school_term_rankings(term)
    specialty_rankings = [
        agg
        for agg in class_rankings
        if getattr(getattr(agg, "student", None), "specialty_id", None) == student.specialty_id
    ]

    class_position = _rank_position(class_rankings, student.id)
    school_position = _rank_position(school_rankings, student.id)
    specialty_position = _rank_position(specialty_rankings, student.id)

    promotion_status = get_promotion_status(student, academic_year, overall_average)
    class_averages = [aggregate.average for aggregate in class_rankings]

    summary = {
        "average": overall_average,
        "class_position": class_position,
        "class_size": len(class_rankings),
        "class_rank_display": _rank_display(class_position, len(class_rankings)),
        "specialty_position": specialty_position,
        "specialty_size": len(specialty_rankings),
        "specialty_rank_display": _rank_display(specialty_position, len(specialty_rankings)),
        "school_position": school_position,
        "school_size": len(school_rankings),
        "school_rank_display": _rank_display(school_position, len(school_rankings)),
        "promotion_status": promotion_status,
        "teacher_remark": _auto_teacher_remark(overall_average),
        "best_average": max(class_averages) if class_averages else None,
        "worst_average": min(class_averages) if class_averages else None,
        "class_average": (sum(class_averages) / len(class_averages)) if class_averages else None,
    }

    ctx = {
        "rows": rows,
        "summary": summary,
        "weights": weights,
        "sequence_cues": _sequence_weight_cues(weights, labels),
        "labels": labels,
        "metadata": _school_report_metadata(school),
    }
    ctx.update(_region_display_context(school))
    ctx["transcript_track"] = getattr(student, "transcript_track", "") or "ACADEMIC"
    ctx["dual_transcript"] = (getattr(student, "transcript_track", "") or "").upper() == "DUAL"
    return ctx


def _annual_average_for_student(student: StudentProfile, terms: Iterable[Term]) -> Optional[float]:
    from django.db.models import Q
    site = _site_settings_for_school(getattr(student, "school", None))
    use_approved_only = getattr(site, "reports_use_approved_grades_only", False)
    term_avgs = []
    for term in terms:
        avg = 0.0
        evals = Evaluation.objects.filter(
            student=student,
            term=term,
            academic_year=term.academic_year,
        )
        if use_approved_only:
            approved_ids, any_request_ids = _approved_or_unrequested_subject_assignment_filter(
                term.academic_year_id, term.id
            )
            evals = evals.filter(
                Q(subject_assignment_id__in=approved_ids) | ~Q(subject_assignment_id__in=any_request_ids)
            )
        if evals.exists():
            total_weighted = 0.0
            total_coef = 0.0
            for e in evals.select_related("subject_assignment"):
                coef = float(e.subject_assignment.coefficient or 1)
                score = float(e.total_score)
                total_weighted += score * coef
                total_coef += coef
            avg = (total_weighted / total_coef) if total_coef else 0.0
            term_avgs.append(avg)

    if not term_avgs:
        return None
    return sum(term_avgs) / len(term_avgs)


def annual_report_context(student: StudentProfile, academic_year) -> dict:
    labels = _resolve_report_labels(student)
    terms = terms_for_student(academic_year, student.classroom)

    term_rows = []
    for term in terms:
        term_avg = _annual_average_for_student(student, [term])
        class_rankings = classroom_term_rankings(student.classroom, term)
        class_position = _rank_position(class_rankings, student.id)
        term_rows.append({
            "term": term.label,
            "avg": term_avg,
            "pos": class_position,
            "class_size": len(class_rankings),
            "rank_display": _rank_display(class_position, len(class_rankings)),
        })

    annual_average = _annual_average_for_student(student, terms)

    class_students = StudentProfile.objects.filter(
        classroom=student.classroom,
        is_active=True,
    ).select_related("classroom")
    specialty_students = StudentProfile.objects.filter(
        classroom=student.classroom,
        specialty_id=student.specialty_id,
        is_active=True,
    ).select_related("classroom")
    school_students = StudentProfile.objects.filter(
        school_id=student.school_id,
        is_active=True,
    ).select_related("classroom")

    class_rankings = sorted(
        class_students,
        key=lambda s: _annual_average_for_student(s, terms) or 0.0,
        reverse=True,
    )
    specialty_rankings = sorted(
        specialty_students,
        key=lambda s: _annual_average_for_student(s, terms) or 0.0,
        reverse=True,
    )
    school_rankings = sorted(
        school_students,
        key=lambda s: _annual_average_for_student(s, terms) or 0.0,
        reverse=True,
    )

    class_position = None
    for idx, s in enumerate(class_rankings, start=1):
        if s.id == student.id:
            class_position = idx
            break

    specialty_position = None
    for idx, s in enumerate(specialty_rankings, start=1):
        if s.id == student.id:
            specialty_position = idx
            break

    school_position = None
    for idx, s in enumerate(school_rankings, start=1):
        if s.id == student.id:
            school_position = idx
            break

    promotion_status = get_promotion_status(student, academic_year, annual_average)
    thresholds = get_promotion_thresholds(student, academic_year) or {}

    ctx = {
        "terms": terms,
        "term_rows": term_rows,
        "annual_average": annual_average,
        "class_position": class_position,
        "class_size": len(class_rankings),
        "class_rank_display": _rank_display(class_position, len(class_rankings)),
        "specialty_position": specialty_position,
        "specialty_size": len(specialty_rankings),
        "specialty_rank_display": _rank_display(specialty_position, len(specialty_rankings)),
        "school_position": school_position,
        "school_size": len(school_rankings),
        "school_rank_display": _rank_display(school_position, len(school_rankings)),
        "promotion_status": promotion_status,
        "promotion_average": thresholds.get("promotion_average"),
        "demotion_average": thresholds.get("demotion_average"),
        "teacher_remark": _auto_teacher_remark(annual_average),
        "labels": labels,
        "metadata": _school_report_metadata(),
    }
    ctx.update(_region_display_context(getattr(student, "school", None)))
    ctx["transcript_track"] = getattr(student, "transcript_track", "") or "ACADEMIC"
    ctx["dual_transcript"] = (getattr(student, "transcript_track", "") or "").upper() == "DUAL"
    return ctx


REPORT_SHARE_DAYS = getattr(settings, "REPORT_SHARE_DAYS", 7)


def build_share_token(report_type: str, student_id: int, academic_year_id: int, term_id: Optional[int]) -> str:
    signer = TimestampSigner(salt="reports.share")
    token_value = f"{report_type}:{student_id}:{academic_year_id}:{term_id or 0}"
    return signer.sign(token_value)


def parse_share_token(token: str) -> Optional[dict]:
    signer = TimestampSigner(salt="reports.share")
    try:
        value = signer.unsign(token, max_age=int(REPORT_SHARE_DAYS * 86400))
    except (BadSignature, SignatureExpired):
        return None

    parts = value.split(":")
    if len(parts) != 4:
        return None

    report_type, student_id, academic_year_id, term_id = parts
    term_value = int(term_id)
    return {
        "report_type": report_type,
        "student_id": int(student_id),
        "academic_year_id": int(academic_year_id),
        "term_id": term_value if term_value != 0 else None,
    }


def build_share_url(request, token: str) -> str:
    return request.build_absolute_uri(reverse("report_share", args=[token]))


def generate_report_qr_code(share_url: str) -> str:
    """Generate a QR code PNG for a report share URL and return as a base64 data-URI.

    The QR code is embedded directly in the report PDF as an <img> tag so that
    anyone holding the paper copy can scan it to verify the report's authenticity
    against the school database.

    Returns a string like "data:image/png;base64,iVBOR..." ready for <img src="">.
    """
    import base64
    import io

    try:
        import qrcode  # qrcode[pil] is in requirements.txt
    except ImportError:
        return ""

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(share_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_regulatory_export(school, preset_id: str, academic_year_id=None, term_id=None):
    """
    Build regulatory/MoE export for the given preset (WAEC, Bulletin, Ofsted, etc.).
    Returns dict with preset_id, template_family, and optionally pdf_url or job_id if generation is implemented.
    """
    from apps.reports.moe_presets import get_moe_preset

    preset = get_moe_preset(preset_id)
    if not preset:
        return {"ok": False, "error": f"Unknown preset: {preset_id}"}
    template_family = preset.get("template_family")
    result = {
        "ok": True,
        "preset_id": preset_id,
        "template_family": template_family,
        "name": preset.get("name"),
        "message": "Use Reports module with this template family for government-compliant PDF. Batch export can be queued via Celery.",
    }
    return result
