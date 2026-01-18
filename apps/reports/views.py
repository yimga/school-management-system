from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Term
from apps.academics.services import get_active_year_and_term
from apps.people.models import StudentGuardian, StudentProfile
from apps.reports.models import ReportCard, TermPublishStatus
from apps.reports.services import (
    annual_report_context,
    are_terms_published,
    build_share_token,
    build_share_url,
    is_term_published,
    parse_share_token,
    term_report_context,
    terms_for_student,
)
from apps.reports.weasy import render_pdf_bytes
from apps.siteconfig.models import SiteSettings


def _reports_enabled() -> bool:
    site = SiteSettings.get_solo()
    return bool(site.enable_reports_pdf)


def _get_guardian_student(request: HttpRequest, student_id: int) -> StudentProfile | None:
    link = (
        StudentGuardian.objects.filter(
            guardian_user=request.user,
            student_id=student_id,
            can_view_results=True,
        )
        .select_related("student")
        .first()
    )
    return link.student if link else None


@role_required(User.Role.PARENT)
def parent_download_term_report(request: HttpRequest, student_id: int):
    if not _reports_enabled():
        return HttpResponseForbidden("PDF reports are disabled by the school.")

    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")

    if term.name == Term.Name.THIRD and not student.classroom.allows_third_term:
        return HttpResponseForbidden("Third term report is not available for this classroom.")

    if not is_term_published(year.id, term.id, student.classroom_id):
        return HttpResponseForbidden("Results not published yet.")

    context = term_report_context(student, year, term)
    context.update({
        "student": student,
        "student_name": f"{student.last_name} {student.first_name}",
        "year": year,
        "term": term,
        "generated_at": timezone.now(),
    })

    pdf_bytes = render_pdf_bytes(request, "reports/term_report.html", context)

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=term,
        student=student,
        type=ReportCard.Type.TERM,
    )
    filename = f"report_{student.student_code}_{year.name}_{term.name}.pdf".replace("/", "-")
    rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@role_required(User.Role.PARENT)
def parent_download_annual_report(request: HttpRequest, student_id: int):
    if not _reports_enabled():
        return HttpResponseForbidden("PDF reports are disabled by the school.")

    year, _term = get_active_year_and_term()
    if not year:
        return HttpResponseForbidden("No active academic year configured yet.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")

    terms = terms_for_student(year, student.classroom)
    if not are_terms_published(year.id, [t.id for t in terms], student.classroom_id):
        return HttpResponseForbidden("Annual report is not available yet.")

    context = annual_report_context(student, year)
    context.update({
        "student": student,
        "student_name": f"{student.last_name} {student.first_name}",
        "year": year,
        "generated_at": timezone.now(),
    })

    pdf_bytes = render_pdf_bytes(request, "reports/annual_report.html", context)

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=None,
        student=student,
        type=ReportCard.Type.ANNUAL,
    )
    filename = f"annual_report_{student.student_code}_{year.name}.pdf".replace("/", "-")
    rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@role_required(User.Role.PARENT)
def parent_share_report(request: HttpRequest, student_id: int, report_type: str):
    if not _reports_enabled():
        return HttpResponseForbidden("PDF reports are disabled by the school.")

    year, term = get_active_year_and_term()
    if not year:
        return HttpResponseForbidden("No active academic year configured yet.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")

    report_type = report_type.upper()
    term_id = None
    if report_type == ReportCard.Type.TERM:
        if not term:
            return HttpResponseForbidden("No active term configured yet.")
        if term.name == Term.Name.THIRD and not student.classroom.allows_third_term:
            return HttpResponseForbidden("Third term report is not available for this classroom.")
        if not is_term_published(year.id, term.id, student.classroom_id):
            return HttpResponseForbidden("Results not published yet.")
        term_id = term.id
    elif report_type == ReportCard.Type.ANNUAL:
        terms = terms_for_student(year, student.classroom)
        if not are_terms_published(year.id, [t.id for t in terms], student.classroom_id):
            return HttpResponseForbidden("Annual report is not available yet.")
    else:
        return HttpResponseForbidden("Unknown report type.")

    token = build_share_token(report_type, student.id, year.id, term_id)
    share_url = build_share_url(request, token)

    if request.method == "POST" and request.POST.get("action") == "email":
        if not request.user.email:
            messages.error(request, "No email address found on your account.")
        elif not getattr(settings, "EMAIL_HOST", "") and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
            messages.error(request, "Email is not configured on the server.")
        else:
            subject = f"{student.last_name} {student.first_name} Report Card"
            body = (
                "A report card link was requested for your student.\n\n"
                f"{share_url}\n\n"
                "This link will expire automatically."
            )
            email = EmailMessage(
                subject=subject,
                body=body,
                to=[request.user.email],
            )
            email.send(fail_silently=True)
            messages.success(request, "Share link emailed successfully.")

    return render(request, "reports/share_link.html", {
        "student": student,
        "year": year,
        "term": term,
        "report_type": report_type,
        "share_url": share_url,
    })


def report_share(request: HttpRequest, token: str):
    if not _reports_enabled():
        return HttpResponseForbidden("PDF reports are disabled by the school.")

    payload = parse_share_token(token)
    if not payload:
        return HttpResponseForbidden("Invalid or expired link.")

    student = get_object_or_404(StudentProfile, id=payload["student_id"])
    year = get_object_or_404(AcademicYear, id=payload["academic_year_id"])
    report_type = payload["report_type"]

    if report_type == ReportCard.Type.TERM:
        term_id = payload.get("term_id")
        if not term_id:
            return HttpResponseForbidden("Invalid link.")
        term = get_object_or_404(Term, id=term_id, academic_year=year)
        if term.name == Term.Name.THIRD and not student.classroom.allows_third_term:
            return HttpResponseForbidden("Third term report is not available for this classroom.")
        if not is_term_published(year.id, term.id, student.classroom_id):
            return HttpResponseForbidden("Results not published yet.")

        context = term_report_context(student, year, term)
        context.update({
            "student": student,
            "student_name": f"{student.last_name} {student.first_name}",
            "year": year,
            "term": term,
            "generated_at": timezone.now(),
        })
        pdf_bytes = render_pdf_bytes(request, "reports/term_report.html", context)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = 'inline; filename="report.pdf"'
        return resp

    if report_type == ReportCard.Type.ANNUAL:
        terms = terms_for_student(year, student.classroom)
        if not are_terms_published(year.id, [t.id for t in terms], student.classroom_id):
            return HttpResponseForbidden("Annual report is not available yet.")

        context = annual_report_context(student, year)
        context.update({
            "student": student,
            "student_name": f"{student.last_name} {student.first_name}",
            "year": year,
            "generated_at": timezone.now(),
        })
        pdf_bytes = render_pdf_bytes(request, "reports/annual_report.html", context)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = 'inline; filename="annual-report.pdf"'
        return resp

    return HttpResponseForbidden("Unknown report type.")


@staff_member_required
def publish_term_results(request: HttpRequest):
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or request.POST.get("year") or str(year.id)
    term_id = request.GET.get("term") or request.POST.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)

    classrooms = Classroom.objects.filter(academic_year=year_obj).order_by("name")

    if request.method == "POST":
        now = timezone.now()
        publish_school = request.POST.get("publish_school") == "1"
        TermPublishStatus.objects.update_or_create(
            academic_year=year_obj,
            term=term_obj,
            classroom=None,
            defaults={
                "is_published": publish_school,
                "published_at": now if publish_school else None,
                "published_by": request.user if publish_school else None,
            },
        )

        selected_classrooms = set(request.POST.getlist("classroom_ids"))
        for classroom in classrooms:
            publish_class = str(classroom.id) in selected_classrooms
            TermPublishStatus.objects.update_or_create(
                academic_year=year_obj,
                term=term_obj,
                classroom=classroom,
                defaults={
                    "is_published": publish_class,
                    "published_at": now if publish_class else None,
                    "published_by": request.user if publish_class else None,
                },
            )

        messages.success(request, "Publish status updated.")
        return redirect(f"{request.path}?year={year_obj.id}&term={term_obj.id}")

    statuses = TermPublishStatus.objects.filter(
        academic_year=year_obj,
        term=term_obj,
    )
    classroom_status = {s.classroom_id: s for s in statuses if s.classroom_id}
    school_status = statuses.filter(classroom__isnull=True, is_published=True).first()

    classroom_states = []
    for classroom in classrooms:
        status = classroom_status.get(classroom.id)
        classroom_states.append({
            "classroom": classroom,
            "is_published": bool(status and status.is_published),
        })

    return render(request, "reports/publish_term.html", {
        "year": year_obj,
        "term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date", "name"),
        "classrooms": classrooms,
        "school_published": bool(school_status),
        "classroom_states": classroom_states,
    })
