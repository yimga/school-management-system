from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.people.models import StudentGuardian
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.reports.models import ReportCard
from apps.reports.services import is_term_published
from apps.reports.pdf import build_term_report_pdf


@role_required(User.Role.PARENT)
def parent_download_term_report(request: HttpRequest, student_id: int):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    link = StudentGuardian.objects.filter(
        guardian_user=request.user,
        student_id=student_id,
        can_view_results=True
    ).select_related("student").first()

    if not link:
        return HttpResponseForbidden("Not authorized.")

    student = link.student

    # publish gate
    if not is_term_published(year.id, term.id, student.classroom_id):
        return HttpResponseForbidden("Results not published yet.")

    evals = Evaluation.objects.filter(
        academic_year=year,
        term=term,
        student=student,
    ).select_related("subject_assignment__subject")

    rows = []
    total_coef = 0.0
    total_weighted = 0.0

    for e in evals:
        coef = float(e.subject_assignment.coefficient)
        marks = [m for m in [e.test1, e.test2] if m is not None]
        avg = float(sum(marks) / len(marks)) if marks else None

        rows.append({
            "subject": e.subject_assignment.subject.name,
            "coef": coef,
            "test1": e.test1,
            "test2": e.test2,
            "avg": avg,
        })

        if avg is not None:
            total_coef += coef
            total_weighted += avg * coef

    overall = (total_weighted / total_coef) if total_coef else None

    pdf_bytes = build_term_report_pdf(
        student_name=f"{student.last_name} {student.first_name}",
        student_code=student.student_code,
        year_name=year.name,
        term_name=term.get_name_display(),
        rows=rows,
        overall=overall,
    )

    # Optional: save/update ReportCard row in DB
    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=term,
        student=student,
        type=ReportCard.Type.TERM,
    )
    filename = f"report_{student.student_code}_{year.name}_{term.name}.pdf".replace("/", "-")
    rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

    # stream to user
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

