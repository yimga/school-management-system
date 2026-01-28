from __future__ import annotations

from typing import Iterable, Optional

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse
from apps.siteconfig.models import SiteSettings

from apps.academics.models import Term
from apps.evals.models import AssessmentWeights, Evaluation
from apps.evals.services import classroom_term_rankings, school_term_rankings
from apps.people.models import StudentProfile
from apps.reports.models import PromotionRule, TermPublishStatus

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


def get_promotion_status(student, academic_year, overall_average):
    if overall_average is None:
        return "NO_DATA"

    rule = _promotion_rule_for_student(student, academic_year)
    if not rule:
        return "PENDING"

    avg = float(overall_average)
    if avg >= float(rule.promotion_average):
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


def _school_report_metadata() -> dict:
    site = SiteSettings.get_solo()
    return {
        "school_name": site.site_name,
        "school_code": site.school_code,
        "country": site.country,
        "region": site.region,
        "ministry": site.ministry,
        "tagline": site.tagline,
    }


def term_report_context(student: StudentProfile, academic_year, term: Term) -> dict:
    evaluations = (
        Evaluation.objects.filter(student=student, term=term, academic_year=academic_year)
        .select_related(
            "subject_assignment__subject",
            "subject_assignment__classroom",
            "subject_assignment__specialty",
        )
        .order_by("subject_assignment__subject__name")
    )

    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=student.classroom,
        term=term,
    )

    rows = []
    total_weighted = 0.0
    total_coef = 0.0

    for e in evaluations:
        coef = float(e.subject_assignment.coefficient or 1)
        total = float(e.total_score)
        rows.append({
            "subject": e.subject_assignment.subject.name,
            "coef": coef,
            "seq1": e.seq1_score if e.seq1_score is not None else e.test1,
            "seq2": e.seq2_score if e.seq2_score is not None else e.test2,
            "exam": e.exam_score,
            "mock": e.mock_score,
            "practical": e.practical_score,
            "total": total,
            "remark": e.remarks,
            "complete": e.is_complete_for_ranking,
        })
        total_weighted += total * coef
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

    summary = {
        "average": overall_average,
        "class_position": class_position,
        "class_size": len(class_rankings),
        "specialty_position": specialty_position,
        "specialty_size": len(specialty_rankings),
        "school_position": school_position,
        "school_size": len(school_rankings),
        "promotion_status": promotion_status,
        "teacher_remark": _auto_teacher_remark(overall_average),
    }

    return {
        "rows": rows,
        "summary": summary,
        "weights": weights,
        "metadata": _school_report_metadata(),
    }


def _annual_average_for_student(student: StudentProfile, terms: Iterable[Term]) -> Optional[float]:
    term_avgs = []
    for term in terms:
        avg = 0.0
        evals = Evaluation.objects.filter(
            student=student,
            term=term,
            academic_year=term.academic_year,
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
    school_students = StudentProfile.objects.filter(is_active=True).select_related("classroom")

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

    return {
        "terms": terms,
        "term_rows": term_rows,
        "annual_average": annual_average,
        "class_position": class_position,
        "class_size": len(class_rankings),
        "specialty_position": specialty_position,
        "specialty_size": len(specialty_rankings),
        "school_position": school_position,
        "school_size": len(school_rankings),
        "promotion_status": promotion_status,
        "promotion_average": thresholds.get("promotion_average"),
        "demotion_average": thresholds.get("demotion_average"),
        "teacher_remark": _auto_teacher_remark(annual_average),
        "metadata": _school_report_metadata(),
    }


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
