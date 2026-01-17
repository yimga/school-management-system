from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden, HttpRequest
from django.db.models import F

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.reports.services import is_term_published


@role_required(User.Role.PARENT)
def parent_dashboard(request: HttpRequest):
    links = StudentGuardian.objects.filter(
        guardian_user=request.user,
        can_view_results=True
    ).select_related("student", "student__classroom", "student__specialty", "student__academic_year")

    return render(request, "parent/dashboard.html", {"links": links})


@role_required(User.Role.PARENT)
def parent_child_results(request: HttpRequest, student_id: int):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    # ensure parent is linked to this student
    link = StudentGuardian.objects.filter(
        guardian_user=request.user,
        student_id=student_id,
        can_view_results=True
    ).select_related("student").first()

    if not link:
        return HttpResponseForbidden("You are not authorized to view this student's results.")

    student = link.student

    # Publish gate: parents only see results if published (school-wide OR class publish)
    published = is_term_published(year.id, term.id, student.classroom_id)
    if not published:
        return render(request, "parent/results.html", {
            "student": student,
            "year": year,
            "term": term,
            "published": False,
            "rows": [],
            "totals": None,
        })

    # Fetch evaluations for that student + active term
    evals = Evaluation.objects.filter(
        academic_year=year,
        term=term,
        student=student,
    ).select_related("subject_assignment__subject")

    # basic totals (coef-weighted)
    rows = []
    total_coef = 0
    total_weighted = 0

    for e in evals:
        coef = float(e.subject_assignment.coefficient)
        avg = e.total_score

        weighted = (avg * coef) if avg is not None else 0
        rows.append({
            "subject": e.subject_assignment.subject.name,
            "coef": coef,
            "seq1": e.seq1_score if e.seq1_score is not None else e.test1,
            "seq2": e.seq2_score if e.seq2_score is not None else e.test2,
            "exam": e.exam_score,
            "mock": e.mock_score,
            "practical": e.practical_score,
            "avg": avg,
        })
        total_coef += coef
        total_weighted += weighted

    overall = (total_weighted / total_coef) if total_coef else None

    return render(request, "parent/results.html", {
        "student": student,
        "year": year,
        "term": term,
        "published": True,
        "rows": rows,
        "totals": {"total_coef": total_coef, "overall": overall},
    })

