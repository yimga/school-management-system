from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import csv
import hashlib
from types import SimpleNamespace

from apps.accounts.decorators import role_required, parent_portal_required
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Term
from apps.academics.services import get_active_year_and_term
from apps.api.rate_limit import throttle_ip_request
from apps.people.models import StudentGuardian, StudentProfile
from apps.reports.models import (
    ReportCard,
    ReportCardAudit,
    ReportDocumentHash,
    TermPublishStatus,
)
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.reports.services import (
    annual_report_context,
    are_terms_published,
    build_share_token,
    build_share_url,
    grade_approval_publish_readiness,
    generate_report_qr_code,
    is_term_published,
    parse_share_token,
    student_has_financial_clearance,
    student_has_outstanding_returns,
    notify_parent_report_blocked_by_debt,
    term_report_context,
    terms_for_student,
)
from apps.platform_runtime.structured_logging import log_view_exception
from apps.reports.weasy import render_pdf_bytes
from apps.siteconfig.models import ReportCardStyle, get_report_card_style_for_student


def _reports_enabled(request: HttpRequest | None = None) -> bool:
    site = get_effective_site_settings(request=request)
    return bool(site.enable_reports_pdf and site.report_downloads_enabled)


def _report_scope_school(request: HttpRequest):
    from apps.schools.models import School, SchoolMembership

    school = getattr(request, "school", None)
    if school is not None:
        return school
    session = getattr(request, "session", None)
    school_id = session.get("school_id") if session is not None else None
    if school_id:
        return School.objects.filter(pk=school_id, is_active=True).first()
    if getattr(request.user, "is_authenticated", False):
        membership = (
            SchoolMembership.objects.filter(user=request.user, school__is_active=True)
            .select_related("school")
            .order_by("-is_primary", "id")
            .first()
        )
        return membership.school if membership else None
    return None


def _active_year_and_term_for_school(school):
    return get_active_year_and_term(school=school)


def _active_year_and_term_for_student(student: StudentProfile):
    return _active_year_and_term_for_school(getattr(student, "school", None))


def _scoped_years_queryset(school):
    years = AcademicYear.objects.all()
    if school is not None:
        years = years.filter(school=school)
    else:
        years = years.filter(school__isnull=True)
    return years.order_by("-start_date")


def _get_guardian_student(
    request: HttpRequest, student_id: int
) -> StudentProfile | None:
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


REPORT_PREVIEW_TEMPLATES = {
    ReportCard.Type.TERM: "reports/preview_term_card.html",
    ReportCard.Type.ANNUAL: "reports/preview_annual_card.html",
}
VERIFY_REPORT_HASH_RATE_LIMIT_WINDOW = 60 * 15
VERIFY_REPORT_HASH_RATE_LIMIT_MAX = 120


def _sample_student(school=None):
    """
    Return a sample student for report preview. When school is provided (tenant context),
    only students from that school are considered. When school is None (e.g. control-plane),
    uses first active student in current schema — do not use in tenant views without passing school.
    """
    qs = StudentProfile.objects.filter(is_active=True).select_related(
        "classroom", "specialty"
    )
    if school is not None:
        qs = qs.filter(school_id=getattr(school, "id", school))
    student = qs.first()
    if student:
        return student
    return SimpleNamespace(
        id=0,
        last_name="Sample",
        first_name="Learner",
        student_code="00SAMPLE",
        classroom=SimpleNamespace(name="Form One"),
        specialty=SimpleNamespace(name="Carpentry"),
    )


def _build_preview_context(
    style: ReportCardStyle, report_type: str, request: HttpRequest | None = None
) -> dict:
    school = _report_scope_school(request) if request else None
    student = _sample_student(school=school)
    year, term = get_active_year_and_term(school=getattr(student, "school", None))
    result = {}
    if report_type == ReportCard.Type.TERM and year and term:
        context = term_report_context(student, year, term)
        result.update(context)
        result.update(
            {
                "student": student,
                "student_name": f"{student.last_name} {student.first_name}",
                "year": year,
                "term": term,
            }
        )
    else:
        context = (
            annual_report_context(student, year)
            if year
            else {"term_rows": [], "annual_average": None}
        )
        result.update(context)
        result.update(
            {
                "student": student,
                "student_name": f"{student.last_name} {student.first_name}",
                "year": year,
            }
        )
    return result


def _log_report_card_action(
    user: User, report_card: ReportCard, action: str, metadata=None
):
    if not report_card:
        return
    if metadata is None:
        metadata = {}
    ReportCardAudit.objects.create(
        report_card=report_card,
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        metadata=metadata,
    )


def _record_report_hash(user: User, report_card: ReportCard, pdf_bytes: bytes):
    """
    Persist SHA-256 digest for generated PDF so external verifiers can validate
    transcript/report authenticity.
    """
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    ReportDocumentHash.objects.update_or_create(
        report_card=report_card,
        defaults={
            "school": getattr(report_card, "school", None),
            "sha256_hash": digest,
            "file_size_bytes": len(pdf_bytes or b""),
            "generated_by": user if getattr(user, "is_authenticated", False) else None,
            "metadata": {
                "student_id": report_card.student_id,
                "academic_year_id": report_card.academic_year_id,
                "term_id": report_card.term_id,
                "type": report_card.type,
            },
        },
    )
    _log_report_card_action(user, report_card, "hash-recorded", {"sha256": digest})


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_download_term_report(request: HttpRequest, student_id: int):
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")
    year, term = _active_year_and_term_for_student(student)
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    if getattr(term, "position", None) == 3 and not student.classroom.allows_third_term:
        return HttpResponseForbidden(
            "Third term report is not available for this classroom."
        )

    if not is_term_published(year.id, term.id, student.classroom_id):
        return HttpResponseForbidden("Results not published yet.")

    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    context = term_report_context(student, year, term)
    context.update(
        {
            "student": student,
            "student_name": f"{student.last_name} {student.first_name}",
            "year": year,
            "term": term,
            "generated_at": timezone.now(),
        }
    )

    # Generate QR code for report authenticity verification
    share_token = build_share_token("term", student.id, year.id, term.id)
    share_url = build_share_url(request, share_token)
    context["qr_code_data_uri"] = generate_report_qr_code(share_url)
    context["verification_url"] = share_url

    style = get_report_card_style_for_student(student, ReportCard.Type.TERM)
    template_name = (
        style.template_for(ReportCard.Type.TERM)
        if style
        else "reports/term_report.html"
    )
    context["report_style"] = style
    pdf_bytes = render_pdf_bytes(request, template_name, context)

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=term,
        student=student,
        type=ReportCard.Type.TERM,
    )
    filename = f"report_{student.student_code}_{year.name}_{term.name}.pdf".replace(
        "/", "-"
    )
    rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
    _record_report_hash(request.user, rc, pdf_bytes)

    _log_report_card_action(request.user, rc, "download-term", {"filename": filename})
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _csv_response(filename: str, headers: list[str], rows: list[list]):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_download_term_report_csv(request: HttpRequest, student_id: int):
    """CSV export of the active term report."""
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")
    year, term = _active_year_and_term_for_student(student)
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    if getattr(term, "position", None) == 3 and not student.classroom.allows_third_term:
        return HttpResponseForbidden(
            "Third term report is not available for this classroom."
        )

    if not is_term_published(year.id, term.id, student.classroom_id):
        return HttpResponseForbidden("Results not published yet.")

    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    context = term_report_context(student, year, term)
    rows = []
    for r in context["rows"]:
        rows.append(
            [
                r["subject"],
                r["coef"],
                r["seq1"],
                r["seq2"],
                r["exam"],
                r["mock"],
                r["practical"],
                r["total"],
                "yes" if r["complete"] else "no",
                r["remark"],
            ]
        )
    summary = context["summary"]
    rows.append([])
    rows.append(
        [
            "Average",
            summary["average"],
            "Class pos",
            summary["class_position"],
            "Size",
            summary["class_size"],
        ]
    )
    filename = (
        f"{student.last_name}_{student.first_name}_{term.name}_{year.name}.csv".replace(
            " ", "_"
        )
    )
    headers = [
        "Subject",
        "Coef",
        "Seq1",
        "Seq2",
        "Exam",
        "Mock",
        "Practical",
        "Total",
        "Complete",
        "Remark",
    ]
    return _csv_response(filename, headers, rows)


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_download_annual_report(request: HttpRequest, student_id: int):
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")
    year, _term = _active_year_and_term_for_student(student)
    if not year:
        return HttpResponseForbidden("No active academic year configured yet.")

    terms = terms_for_student(year, student.classroom)
    if not are_terms_published(year.id, [t.id for t in terms], student.classroom_id):
        return HttpResponseForbidden("Annual report is not available yet.")

    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    context = annual_report_context(student, year)
    context.update(
        {
            "student": student,
            "student_name": f"{student.last_name} {student.first_name}",
            "year": year,
            "generated_at": timezone.now(),
        }
    )

    # QR code for annual report verification
    share_token = build_share_token("annual", student.id, year.id, None)
    share_url = build_share_url(request, share_token)
    context["qr_code_data_uri"] = generate_report_qr_code(share_url)
    context["verification_url"] = share_url

    style = get_report_card_style_for_student(student, ReportCard.Type.ANNUAL)
    template_name = (
        style.template_for(ReportCard.Type.ANNUAL)
        if style
        else "reports/annual_report.html"
    )
    context["report_style"] = style
    pdf_bytes = render_pdf_bytes(request, template_name, context)

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=None,
        student=student,
        type=ReportCard.Type.ANNUAL,
    )
    filename = f"annual_report_{student.student_code}_{year.name}.pdf".replace("/", "-")
    rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
    _record_report_hash(request.user, rc, pdf_bytes)

    _log_report_card_action(request.user, rc, "download-annual", {"filename": filename})
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@require_http_methods(["GET"])
def verify_report_hash(request: HttpRequest):
    """
    Public verification endpoint for report hash ledger.
    Query:
      - hash=<sha256> OR
      - report_card_id=<id>
    """
    allowed, retry_after = throttle_ip_request(
        request,
        scope="reports:verify_hash",
        max_count=VERIFY_REPORT_HASH_RATE_LIMIT_MAX,
        window_seconds=VERIFY_REPORT_HASH_RATE_LIMIT_WINDOW,
    )
    if not allowed:
        response = JsonResponse(
            {"verified": False, "error": "Too many requests"}, status=429
        )
        response["Retry-After"] = str(retry_after)
        return response

    sha = (request.GET.get("hash") or "").strip().lower()
    report_card_id = (request.GET.get("report_card_id") or "").strip()
    row = None
    if sha:
        row = (
            ReportDocumentHash.objects.filter(sha256_hash=sha)
            .select_related("report_card")
            .first()
        )
    elif report_card_id.isdigit():
        row = (
            ReportDocumentHash.objects.filter(report_card_id=int(report_card_id))
            .select_related("report_card")
            .first()
        )
    else:
        return JsonResponse(
            {"verified": False, "error": "Provide hash or report_card_id"}, status=400
        )

    if not row:
        return JsonResponse({"verified": False, "error": "Hash not found"}, status=404)

    rc = row.report_card
    return JsonResponse(
        {
            "verified": True,
            "sha256": row.sha256_hash,
            "report_card_id": rc.pk,
            "student_id": rc.student_id,
            "type": rc.type,
            "academic_year_id": rc.academic_year_id,
            "term_id": rc.term_id,
            "file_size_bytes": row.file_size_bytes,
            "created_at": row.created_at.isoformat(),
        },
        status=200,
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_download_annual_report_csv(request: HttpRequest, student_id: int):
    """CSV export of annual report (all terms)."""
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")
    year, _term = _active_year_and_term_for_student(student)
    if not year:
        return HttpResponseForbidden("No active academic year configured yet.")

    terms_annual = terms_for_student(year, student.classroom)
    if not are_terms_published(
        year.id, [t.id for t in terms_annual], student.classroom_id
    ):
        return HttpResponseForbidden("Annual report is not available yet.")
    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    context = annual_report_context(student, year)
    rows = []
    for term_row in context["term_rows"]:
        rows.append(
            [
                term_row["term"],
                term_row["avg"],
                term_row["pos"],
                term_row["class_size"],
            ]
        )
    rows.append([])
    rows.append(
        [
            "Annual average",
            context["annual_average"],
            "Class position",
            context["class_position"],
            "School position",
            context["school_position"],
        ]
    )
    filename = (
        f"{student.last_name}_{student.first_name}_annual_{year.name}.csv".replace(
            " ", "_"
        )
    )
    headers = ["Term", "Average", "Class position", "Class size"]
    return _csv_response(filename, headers, rows)


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_share_report(request: HttpRequest, student_id: int, report_type: str):
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    student = _get_guardian_student(request, student_id)
    if not student:
        return HttpResponseForbidden("Not authorized.")
    year, term = _active_year_and_term_for_student(student)
    if not year:
        return HttpResponseForbidden("No active academic year configured yet.")

    report_type = report_type.upper()
    term_id = None
    if report_type == ReportCard.Type.TERM:
        if not term:
            return HttpResponseForbidden("No active term configured yet.")
        if (
            getattr(term, "position", None) == 3
            and not student.classroom.allows_third_term
        ):
            return HttpResponseForbidden(
                "Third term report is not available for this classroom."
            )
        if not is_term_published(year.id, term.id, student.classroom_id):
            return HttpResponseForbidden("Results not published yet.")
        term_id = term.id
    elif report_type == ReportCard.Type.ANNUAL:
        terms = terms_for_student(year, student.classroom)
        if not are_terms_published(
            year.id, [t.id for t in terms], student.classroom_id
        ):
            return HttpResponseForbidden("Annual report is not available yet.")
    else:
        return HttpResponseForbidden("Unknown report type.")

    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    token = build_share_token(report_type, student.id, year.id, term_id)
    share_url = build_share_url(request, token)

    if request.method == "POST" and request.POST.get("action") == "email":
        if not request.user.email:
            messages.error(request, "No email address found on your account.")
        elif not getattr(
            settings, "EMAIL_HOST", ""
        ) and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
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

    site = get_effective_site_settings(request=request)
    enable_whatsapp_share = getattr(site, "enable_whatsapp_parent_portal", False)
    return render(
        request,
        "reports/share_link.html",
        {
            "student": student,
            "year": year,
            "term": term,
            "report_type": report_type,
            "share_url": share_url,
            "enable_whatsapp_share": enable_whatsapp_share,
        },
    )


def report_share(request: HttpRequest, token: str):
    site = get_effective_site_settings(request=request)
    if not site.enable_parent_portal:
        return HttpResponseForbidden("Parent portal is disabled.")
    if not _reports_enabled(request):
        return HttpResponseForbidden("Report downloads are disabled by the school.")

    payload = parse_share_token(token)
    if not payload:
        return HttpResponseForbidden("Invalid or expired link.")

    student = get_object_or_404(StudentProfile, id=payload["student_id"])
    year = get_object_or_404(AcademicYear, id=payload["academic_year_id"])
    report_type = payload["report_type"]
    if (
        getattr(student, "school_id", None)
        and getattr(year, "school_id", None)
        and student.school_id != year.school_id
    ):
        return HttpResponseForbidden("Invalid link.")

    if not student_has_financial_clearance(student, year):
        notify_parent_report_blocked_by_debt(student, year)
        return HttpResponseForbidden(
            "Report card is not available until fees are cleared. Please visit the Bursary."
        )
    if student_has_outstanding_returns(student, year):
        return HttpResponseForbidden(
            "Report card is not available until all issued resources are returned."
        )

    if report_type == ReportCard.Type.TERM:
        term_id = payload.get("term_id")
        if not term_id:
            return HttpResponseForbidden("Invalid link.")
        term = get_object_or_404(Term, id=term_id, academic_year=year)
        if (
            getattr(term, "position", None) == 3
            and not student.classroom.allows_third_term
        ):
            return HttpResponseForbidden(
                "Third term report is not available for this classroom."
            )
        if not is_term_published(year.id, term.id, student.classroom_id):
            return HttpResponseForbidden("Results not published yet.")

        context = term_report_context(student, year, term)
        context.update(
            {
                "student": student,
                "student_name": f"{student.last_name} {student.first_name}",
                "year": year,
                "term": term,
                "generated_at": timezone.now(),
            }
        )
        style = get_report_card_style_for_student(student, ReportCard.Type.TERM)
        template_name = (
            style.template_for(ReportCard.Type.TERM)
            if style
            else "reports/term_report.html"
        )
        context["report_style"] = style
        pdf_bytes = render_pdf_bytes(request, template_name, context)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = 'inline; filename="report.pdf"'
        return resp

    if report_type == ReportCard.Type.ANNUAL:
        terms = terms_for_student(year, student.classroom)
        if not are_terms_published(
            year.id, [t.id for t in terms], student.classroom_id
        ):
            return HttpResponseForbidden("Annual report is not available yet.")

        context = annual_report_context(student, year)
        context.update(
            {
                "student": student,
                "student_name": f"{student.last_name} {student.first_name}",
                "year": year,
                "generated_at": timezone.now(),
            }
        )
        style = get_report_card_style_for_student(student, ReportCard.Type.ANNUAL)
        template_name = (
            style.template_for(ReportCard.Type.ANNUAL)
            if style
            else "reports/annual_report.html"
        )
        context["report_style"] = style
        pdf_bytes = render_pdf_bytes(request, template_name, context)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = 'inline; filename="annual-report.pdf"'
        return resp

    return HttpResponseForbidden("Unknown report type.")


@staff_member_required(login_url=settings.LOGIN_URL)
def publish_term_results(request: HttpRequest):
    school = _report_scope_school(request)
    year, active_term = _active_year_and_term_for_school(school)
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or request.POST.get("year") or str(year.id)
    term_id = request.GET.get("term") or request.POST.get("term") or str(active_term.id)

    year_queryset = AcademicYear.objects.filter(id=year_id)
    if school is not None:
        year_queryset = year_queryset.filter(school=school)
    else:
        year_queryset = year_queryset.filter(school__isnull=True)
    year_obj = get_object_or_404(year_queryset)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)

    classrooms = Classroom.objects.filter(academic_year=year_obj)
    if school is not None:
        classrooms = classrooms.filter(school=school)
    else:
        classrooms = classrooms.filter(school__isnull=True)
    classrooms = classrooms.order_by("name")

    site = get_effective_site_settings(request=request)
    require_approved_before_publish = getattr(
        site, "reports_require_approved_grades_before_publish", False
    )
    grade_approval_enabled = getattr(site, "grade_approval_enabled", False)
    approval_state = grade_approval_publish_readiness(year_obj.id, term_obj.id)
    pending_approvals = approval_state["pending_count"]
    rejected_approvals = approval_state["rejected_count"]
    missing_approvals = approval_state["missing_count"]
    all_grades_approved = approval_state["ready_for_publish"]
    subject_assignments_with_grades = approval_state["subject_assignments_with_grades"]
    approved_grade_approvals = approval_state["approved_count"]

    if request.method == "POST":
        publish_school = request.POST.get("publish_school") == "1"
        valid_classroom_ids = {str(c.id) for c in classrooms}
        selected_classrooms = {
            classroom_id
            for classroom_id in request.POST.getlist("classroom_ids")
            if classroom_id in valid_classroom_ids
        }
        publish_intent = publish_school or bool(selected_classrooms)

        scoped_approval_state = approval_state
        if publish_intent:
            scoped_classroom_ids = None
            if not publish_school:
                scoped_classroom_ids = [
                    int(classroom_id) for classroom_id in selected_classrooms
                ]
            scoped_approval_state = grade_approval_publish_readiness(
                year_obj.id,
                term_obj.id,
                classroom_ids=scoped_classroom_ids,
            )
            pending_approvals = scoped_approval_state["pending_count"]
            rejected_approvals = scoped_approval_state["rejected_count"]
            missing_approvals = scoped_approval_state["missing_count"]
            all_grades_approved = scoped_approval_state["ready_for_publish"]
            subject_assignments_with_grades = scoped_approval_state[
                "subject_assignments_with_grades"
            ]
            approved_grade_approvals = scoped_approval_state["approved_count"]

        if (
            require_approved_before_publish
            and grade_approval_enabled
            and publish_intent
            and not all_grades_approved
        ):
            messages.error(
                request,
                "Cannot publish: grade approvals are incomplete for this term "
                f"(pending: {pending_approvals}, rejected: {rejected_approvals}, missing: {missing_approvals}). "
                "Approve or resubmit in Evals -> Grade approvals, or turn off 'Require approved grades before publish' in Site Settings.",
            )
        else:
            now = timezone.now()
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
            try:
                from apps.compliance.models_audit import AuditLog

                AuditLog.objects.create(
                    action=AuditLog.Action.PUBLISH,
                    user=request.user,
                    model_name="TermPublishStatus",
                    object_id=f"{year_obj.id}_{term_obj.id}",
                    object_repr=f"{year_obj} {term_obj}",
                    app_label="reports",
                    new_values={
                        "publish_school": publish_school,
                        "classroom_ids": list(selected_classrooms),
                    },
                )
            except (
                DatabaseError,
                IntegrityError,
                ValidationError,
                TypeError,
                ValueError,
            ):
                log_view_exception(
                    request,
                    "reports publish: AuditLog create failed",
                    extra={
                        "academic_year_id": getattr(year_obj, "id", None),
                        "term_id": getattr(term_obj, "id", None),
                        "publish_school": publish_school,
                    },
                )
            # Phase 3: Award Honor Roll badges for students in published classrooms
            published_classroom_ids = (
                {str(c.id) for c in classrooms}
                if publish_school
                else selected_classrooms
            )
            if published_classroom_ids:
                from apps.people.badge_services import (
                    create_honor_roll_badge_for_student,
                )

                for classroom in classrooms:
                    if str(classroom.id) not in published_classroom_ids:
                        continue
                    for student in StudentProfile.objects.filter(
                        classroom=classroom,
                        academic_year=year_obj,
                        school=school,
                        is_active=True,
                        deleted_at__isnull=True,
                    ):
                        try:
                            ctx = term_report_context(student, year_obj, term_obj)
                            avg = ctx.get("average")
                            if avg is not None:
                                create_honor_roll_badge_for_student(
                                    student, year_obj, term_obj, avg
                                )
                        except (
                            DatabaseError,
                            IntegrityError,
                            ValidationError,
                            TypeError,
                            ValueError,
                            KeyError,
                            ObjectDoesNotExist,
                        ):
                            log_view_exception(
                                request,
                                "reports publish: honor roll badge create failed",
                                extra={
                                    "school_id": getattr(school, "id", None),
                                    "student_id": getattr(student, "id", None),
                                    "academic_year_id": getattr(year_obj, "id", None),
                                    "term_id": getattr(term_obj, "id", None),
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
        classroom_states.append(
            {
                "classroom": classroom,
                "is_published": bool(status and status.is_published),
            }
        )

    return render(
        request,
        "reports/publish_term.html",
        {
            "year": year_obj,
            "term": term_obj,
            "years": _scoped_years_queryset(school),
            "terms": Term.objects.filter(academic_year=year_obj).order_by(
                "start_date", "name"
            ),
            "classrooms": classrooms,
            "school_published": bool(school_status),
            "classroom_states": classroom_states,
            "pending_grade_approvals": pending_approvals,
            "rejected_grade_approvals": rejected_approvals,
            "missing_grade_approvals": missing_approvals,
            "subject_assignments_with_grades": subject_assignments_with_grades,
            "approved_grade_approvals": approved_grade_approvals,
            "all_grades_approved": all_grades_approved,
            "grade_approval_enabled": grade_approval_enabled,
            "reports_require_approved_grades_before_publish": require_approved_before_publish,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def statistical_return(request: HttpRequest):
    """
    Annual statistical return for regional/Ministry submission: success rates, gender ratio, teacher-student ratio by class.
    """
    from apps.reports.services import get_promotion_status, _annual_average_for_student
    from apps.people.models import TeacherProfile

    school = _report_scope_school(request)
    if school is None:
        return HttpResponseForbidden("School context required.")

    years = list(_scoped_years_queryset(school))
    year_id = request.GET.get("year") or (years[0].id if years else None)
    export = request.GET.get("export") == "csv"

    if not year_id:
        return render(
            request,
            "reports/statistical_return.html",
            {"years": years, "year": None, "rows": [], "totals": None},
        )

    year_obj = get_object_or_404(AcademicYear, id=year_id, school=school)
    terms = list(
        Term.objects.filter(academic_year=year_obj).order_by("position", "start_date")
    )
    classrooms = list(
        Classroom.objects.filter(academic_year=year_obj, school=school).order_by("name")
    )

    rows = []
    total_students = 0
    total_male = 0
    total_female = 0
    total_promoted = 0

    for classroom in classrooms:
        students = list(
            StudentProfile.objects.filter(
                academic_year=year_obj,
                classroom=classroom,
                school=school,
                is_active=True,
            ).select_related("classroom")
        )
        male = sum(1 for s in students if getattr(s, "gender", None) == "MALE")
        female = sum(1 for s in students if getattr(s, "gender", None) == "FEMALE")
        promoted = 0
        for s in students:
            avg = _annual_average_for_student(s, terms) if terms else None
            if get_promotion_status(s, year_obj, avg) == "PROMOTED":
                promoted += 1
        n = len(students)
        total_students += n
        total_male += male
        total_female += female
        total_promoted += promoted
        success_rate = (promoted / n * 100) if n else 0
        rows.append(
            {
                "classroom": classroom.name,
                "students": n,
                "male": male,
                "female": female,
                "promoted": promoted,
                "success_rate": round(success_rate, 1),
            }
        )

    teacher_count = TeacherProfile.objects.filter(is_active=True, school=school).count()
    totals = {
        "students": total_students,
        "male": total_male,
        "female": total_female,
        "promoted": total_promoted,
        "success_rate": round((total_promoted / total_students * 100), 1)
        if total_students
        else 0,
        "teachers": teacher_count,
        "teacher_student_ratio": round(teacher_count / total_students, 2)
        if total_students
        else None,
    }

    if export:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="statistical_return_{year_obj.name.replace("/", "-")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            ["Classroom", "Students", "Male", "Female", "Promoted", "Success %"]
        )
        for r in rows:
            writer.writerow(
                [
                    r["classroom"],
                    r["students"],
                    r["male"],
                    r["female"],
                    r["promoted"],
                    r["success_rate"],
                ]
            )
        writer.writerow([])
        writer.writerow(
            [
                "Total",
                totals["students"],
                totals["male"],
                totals["female"],
                totals["promoted"],
                totals["success_rate"],
            ]
        )
        writer.writerow(["Teachers", totals["teachers"], "", "", "", ""])
        writer.writerow(
            [
                "Teacher/student ratio",
                totals["teacher_student_ratio"] or "",
                "",
                "",
                "",
                "",
            ]
        )
        return response

    return render(
        request,
        "reports/statistical_return.html",
        {
            "years": years,
            "year": year_obj,
            "rows": rows,
            "totals": totals,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def promotion_preview(request: HttpRequest):
    """
    Promotion preview / borderline list: by academic year, list students with annual average,
    promotion status (PROMOTED/REPEAT/DEMOTED/NO_DATA), and borderline flag for deliberation council.
    Borderline = average >= demotion and < promotion threshold (e.g. 9.0–10.0 when threshold is 10).
    """
    from apps.reports.services import (
        get_promotion_status,
        get_promotion_thresholds,
        _annual_average_for_student,
    )

    school = _report_scope_school(request)
    if school is None:
        return HttpResponseForbidden("School context required.")

    years = list(_scoped_years_queryset(school))
    year_id = request.GET.get("year") or (years[0].id if years else None)
    export = request.GET.get("export") == "csv"

    if not year_id:
        return render(
            request,
            "reports/promotion_preview.html",
            {"years": years, "year": None, "by_classroom": [], "borderline_count": 0},
        )

    year_obj = get_object_or_404(AcademicYear, id=year_id, school=school)
    terms = list(
        Term.objects.filter(academic_year=year_obj).order_by("position", "start_date")
    )
    classrooms_qs = Classroom.objects.filter(
        academic_year=year_obj, school=school
    ).order_by("name")
    classroom_id = request.GET.get("classroom")
    if classroom_id:
        classrooms_qs = classrooms_qs.filter(id=classroom_id)
    classrooms = list(classrooms_qs)

    by_classroom = []
    borderline_count = 0
    flat_rows = []

    for classroom in classrooms:
        students = list(
            StudentProfile.objects.filter(
                academic_year=year_obj,
                classroom=classroom,
                school=school,
                is_active=True,
            ).select_related("classroom")
        )
        student_rows = []
        for s in students:
            annual_avg = _annual_average_for_student(s, terms) if terms else None
            promo = (
                get_promotion_status(s, year_obj, annual_avg)
                if annual_avg is not None
                else "NO_DATA"
            )
            thresholds = get_promotion_thresholds(s, year_obj)
            promo_avg = float(thresholds["promotion_average"]) if thresholds else 10.0
            demotion_avg = float(thresholds["demotion_average"]) if thresholds else 0.0
            is_borderline = False
            if annual_avg is not None and thresholds:
                is_borderline = demotion_avg <= annual_avg < promo_avg
                if is_borderline:
                    borderline_count += 1
            row_data = {
                "classroom": classroom,
                "student": s,
                "annual_average": round(annual_avg, 2)
                if annual_avg is not None
                else None,
                "promotion_status": promo,
                "is_borderline": is_borderline,
            }
            student_rows.append(row_data)
            flat_rows.append(row_data)
        by_classroom.append(
            {
                "classroom": classroom,
                "students": student_rows,
            }
        )

    if export:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="promotion_preview_{year_obj.name.replace("/", "-")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            ["Classroom", "Student", "Annual average", "Promotion status", "Borderline"]
        )
        for group in by_classroom:
            for row in group["students"]:
                name = (
                    row["student"].get_full_name() or row["student"].last_name or ""
                ).strip()
                writer.writerow(
                    [
                        group["classroom"].name,
                        name,
                        row["annual_average"]
                        if row["annual_average"] is not None
                        else "",
                        row["promotion_status"],
                        "Yes" if row["is_borderline"] else "No",
                    ]
                )
        return response

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(flat_rows, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()
    all_classrooms = list(
        Classroom.objects.filter(academic_year=year_obj, school=school).order_by("name")
    )

    return render(
        request,
        "reports/promotion_preview.html",
        {
            "years": years,
            "year": year_obj,
            "by_classroom": by_classroom,
            "borderline_count": borderline_count,
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
            "classrooms": all_classrooms,
            "selected_classroom": classroom_id or "",
        },
    )


def _regulatory_export_school(request: HttpRequest):
    """Resolve school for regulatory export: request.school, session, or first membership."""
    return _report_scope_school(request)


def regulatory_export(request: HttpRequest):
    """
    Regulatory / MoE export: list presets (WAEC, Bulletin de Notes, Ofsted, etc.)
    and allow one-click export by preset. Staff only.
    POST: preset_id, academic_year_id?, term_id? → run build_regulatory_export and show result.
    """
    from apps.reports.moe_presets import get_moe_presets
    from apps.reports.services import build_regulatory_export

    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL + "?next=" + request.path)
    if not (
        request.user.is_staff
        or (getattr(request.user, "role", "") or "").upper()
        in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "BURSAR")
    ):
        return HttpResponseForbidden("Staff only.")
    presets = get_moe_presets()

    # POST: run export
    export_result = None
    if request.method == "POST":
        school = _regulatory_export_school(request)
        if not school:
            export_result = {
                "ok": False,
                "error": "Select a school (backend/session) to run export.",
            }
        else:
            preset_id = (request.POST.get("preset_id") or "").strip()
            if not preset_id:
                export_result = {"ok": False, "error": "preset_id required."}
            else:
                academic_year_id = request.POST.get("academic_year_id") or None
                term_id = request.POST.get("term_id") or None
                if academic_year_id:
                    try:
                        academic_year_id = int(academic_year_id)
                    except (TypeError, ValueError):
                        academic_year_id = None
                if term_id:
                    try:
                        term_id = int(term_id)
                    except (TypeError, ValueError):
                        term_id = None
                export_result = build_regulatory_export(
                    school,
                    preset_id,
                    academic_year_id=academic_year_id,
                    term_id=term_id,
                )
        if (
            request.headers.get("Accept", "").find("application/json") >= 0
            or request.GET.get("format") == "json"
        ):
            return JsonResponse(export_result or {})

    if (
        request.headers.get("Accept", "").find("application/json") >= 0
        or request.GET.get("format") == "json"
    ):
        return JsonResponse({"presets": presets})
    # Years/terms for dropdowns
    school_for_years = _regulatory_export_school(request)
    years = []
    if school_for_years:
        years = list(
            AcademicYear.objects.filter(school=school_for_years).order_by(
                "-start_date"
            )[:20]
        )
    terms = (
        list(Term.objects.filter(academic_year_id=years[0].id).order_by("start_date"))
        if years
        else []
    )
    return render(
        request,
        "reports/regulatory_export.html",
        {
            "presets": presets,
            "export_result": export_result,
            "academic_years": years,
            "terms": terms,
        },
    )
