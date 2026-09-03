from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
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

from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import role_required, parent_portal_required, require_permission
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Term
from apps.academics.services import get_active_year_and_term
from apps.api.rate_limit import throttle_ip_request
from apps.compliance.decorators import audit_pii_view
from apps.people.models import StudentGuardian, StudentProfile
from apps.reports.models import (
    ReportCard,
    ReportCardAudit,
    ReportDocumentHash,
    TermPublishStatus,
)
from apps.siteconfig.config_service import get_effective_site_settings
from apps.platform_runtime.config_resolver import get_effective_config
from apps.reports.services import (
    annual_report_context,
    are_terms_published,
    build_share_token,
    build_share_url,
    grade_approval_publish_readiness,
    generate_report_qr_code,
    is_term_published,
    parse_share_token,
    financial_clearance_block_message,
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
    return bool(
        get_effective_config(key="enable_reports_pdf", request=request)
        and get_effective_config(key="report_downloads_enabled", request=request)
    )


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
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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
    # tenant-isolation-allow: view-scoped-via-request-school
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
        StudentGuardian.objects.filter(  # tenant-isolation-allow: guardianship check on one (user, student) pair (reviewed 2026-09-03)
            guardian_user=request.user,
            student_id=student_id,
            can_view_results=True,
        )
        .select_related("student")
        .first()
    )
    return link.student if link else None


VERIFY_REPORT_HASH_RATE_LIMIT_WINDOW = 60 * 15
VERIFY_REPORT_HASH_RATE_LIMIT_MAX = 120


def _sample_student(school=None):
    """
    Return a sample student for report preview. When school is provided (tenant context),
    only students from that school are considered. When school is None (e.g. control-plane),
    uses first active student in current schema — do not use in tenant views without passing school.
    """
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    qs = StudentProfile.objects.filter(is_active=True).select_related(
        "classroom", "specialty"
    )
    if school is not None:
        qs = qs.filter(school_id=getattr(school, "id", school))
    student = qs.first()
    if student:
        return student
    # Pass 8: previously returned "Sample Learner / 00SAMPLE / Form One / Carpentry"
    # which leaked into live report-card previews for tenants without students. Replaced
    # with neutral angle-bracket placeholders so the preview reads as "fill this in"
    # rather than as fake student data the tenant might mistake for real.
    return SimpleNamespace(
        id=0,
        last_name="<Last name>",
        first_name="<First name>",
        student_code="<Student code>",
        classroom=SimpleNamespace(name="<Classroom>"),
        specialty=SimpleNamespace(name="<Specialty>"),
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


def _report_card_is_frozen(report_card: ReportCard) -> bool:
    """A report card is FROZEN once its verification hash has been recorded."""
    # tenant-isolation-allow: hash-scoped-via-single-report-card-instance
    return ReportDocumentHash.objects.filter(report_card=report_card).exists()


def _frozen_pdf_bytes(report_card: ReportCard) -> bytes | None:
    """Return the stored (frozen) PDF bytes iff this report card was already
    frozen — a ReportDocumentHash exists AND ``pdf_file`` is present and readable.

    Returns ``None`` to signal "not yet frozen; render + freeze now". Serving the
    stored bytes (rather than re-rendering) is what makes a published report card
    immutable: the downloaded document always matches the recorded SHA-256.
    """
    if not getattr(report_card, "pdf_file", None):
        return None
    if not _report_card_is_frozen(report_card):
        return None
    try:
        with report_card.pdf_file.open("rb") as fh:
            data = fh.read()
    except (OSError, ValueError):
        return None
    return data or None


def _record_report_hash(user: User, report_card: ReportCard, pdf_bytes: bytes):
    """
    Persist SHA-256 digest for a generated PDF so external verifiers can validate
    transcript/report authenticity.

    FREEZE-ONCE (immutable ledger): the FIRST recorded hash is authoritative
    forever. A previous ``update_or_create`` here silently overwrote the digest on
    every re-render, so the "immutable" verification record drifted whenever the
    template, fonts, or a corrected grade changed the bytes — quietly invalidating
    any credential a parent had already verified. Now:
      * no hash yet  -> create it (this is the freeze / publish moment);
      * same digest  -> idempotent no-op (verified);
      * new digest   -> the frozen hash is NOT overwritten; the divergence is
                        recorded in metadata for audit and surfaced in the log.
    """
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    # tenant-isolation-allow: hash-scoped-via-single-report-card-instance
    existing = ReportDocumentHash.objects.filter(report_card=report_card).first()
    if existing is not None:
        if existing.sha256_hash == digest:
            _log_report_card_action(
                user, report_card, "hash-verified", {"sha256": digest}
            )
            return
        # Immutability guarantee: keep the original, never overwrite. Record the
        # divergent digest (bounded) so an audit can see a re-render drifted.
        meta = dict(existing.metadata or {})
        divergences = list(meta.get("divergent_digests") or [])
        if digest not in divergences:
            divergences.append(digest)
            meta["divergent_digests"] = divergences[-10:]
            existing.metadata = meta
            existing.save(update_fields=["metadata"])
        _log_report_card_action(
            user,
            report_card,
            "hash-divergence",
            {"frozen": existing.sha256_hash, "recomputed": digest},
        )
        return

    ReportDocumentHash.objects.create(
        report_card=report_card,
        school=getattr(report_card, "school", None),
        sha256_hash=digest,
        file_size_bytes=len(pdf_bytes or b""),
        generated_by=user if getattr(user, "is_authenticated", False) else None,
        metadata={
            "student_id": report_card.student_id,
            "academic_year_id": report_card.academic_year_id,
            "term_id": report_card.term_id,
            "type": report_card.type,
        },
    )
    _log_report_card_action(user, report_card, "hash-recorded", {"sha256": digest})


def _record_report_card_lineage(report_card, context: dict) -> None:
    """Stamp derived-value lineage at generation time (2026-07-02).

    Term reports carry row-level provenance (the exact Evaluation rows the
    context builder read); annual reports aggregate per-term averages without
    materializing rows, so their lineage is an honest scope descriptor.
    """
    from apps.metadata.models_derived_lineage import record_derived_lineage

    evaluation_ids = context.get("lineage_evaluation_ids")
    if evaluation_ids:
        record_derived_lineage(
            output=report_card,
            computation="report_card.term",
            granularity="row",
            inputs=[{"model": "evals.Evaluation", "pk": str(pk)} for pk in evaluation_ids],
        )
    else:
        record_derived_lineage(
            output=report_card,
            computation="report_card.annual",
            granularity="scope",
            inputs=[
                {
                    "model": "evals.Evaluation",
                    "scope": {
                        "student": str(report_card.student_id),
                        "academic_year": str(report_card.academic_year_id),
                    },
                }
            ],
        )


@parent_portal_required
@role_required(User.Role.PARENT)
@audit_pii_view(model_name="ReportCard", object_id_kwarg="student_id", sensitivity="HIGH", reason="Parent term report PDF download")
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
            financial_clearance_block_message(student, year)
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

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=term,
        student=student,
        type=ReportCard.Type.TERM,
        defaults={"school": student.school},
    )
    if rc.school_id is None and getattr(student, "school_id", None):
        # Stamp the owning school so tenant-host QR/hash verification resolves:
        # verify_report_hash filters report_card__school=request.school, so a
        # NULL-school row 404s for every tenant. Also heals legacy rows created
        # before school was stamped.
        rc.school = student.school
        rc.save(update_fields=["school"])
    filename = f"report_{student.student_code}_{year.name}_{term.name}.pdf".replace(
        "/", "-"
    )

    # Immutable archive: once a report card is published (frozen), serve the
    # STORED pdf_file verbatim so the bytes always match the recorded hash — never
    # silently re-render. Only the first download renders, persists, and freezes.
    pdf_bytes = _frozen_pdf_bytes(rc)
    if pdf_bytes is None:
        pdf_bytes = render_pdf_bytes(request, template_name, context)
        rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
        _record_report_hash(request.user, rc, pdf_bytes)
        _record_report_card_lineage(rc, context)
        _log_report_card_action(request.user, rc, "download-term", {"filename": filename})
    else:
        _log_report_card_action(
            request.user, rc, "download-term-frozen", {"filename": filename}
        )
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
@audit_pii_view(model_name="ReportCard", object_id_kwarg="student_id", sensitivity="HIGH", reason="Parent term report CSV download")
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
            financial_clearance_block_message(student, year)
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
@audit_pii_view(model_name="ReportCard", object_id_kwarg="student_id", sensitivity="HIGH", reason="Parent annual report PDF download")
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
            financial_clearance_block_message(student, year)
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

    rc, _ = ReportCard.objects.get_or_create(
        academic_year=year,
        term=None,
        student=student,
        type=ReportCard.Type.ANNUAL,
        defaults={"school": student.school},
    )
    if rc.school_id is None and getattr(student, "school_id", None):
        # Stamp the owning school so tenant-host QR/hash verification resolves:
        # verify_report_hash filters report_card__school=request.school, so a
        # NULL-school row 404s for every tenant. Also heals legacy rows created
        # before school was stamped.
        rc.school = student.school
        rc.save(update_fields=["school"])
    filename = f"annual_report_{student.student_code}_{year.name}.pdf".replace("/", "-")

    # Immutable archive: serve the frozen PDF verbatim once published; only the
    # first download renders, persists, and freezes (hash + stored file).
    pdf_bytes = _frozen_pdf_bytes(rc)
    if pdf_bytes is None:
        pdf_bytes = render_pdf_bytes(request, template_name, context)
        rc.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
        _record_report_hash(request.user, rc, pdf_bytes)
        _record_report_card_lineage(rc, context)
        _log_report_card_action(
            request.user, rc, "download-annual", {"filename": filename}
        )
    else:
        _log_report_card_action(
            request.user, rc, "download-annual-frozen", {"filename": filename}
        )
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
    school = getattr(request, "school", None)
    row = None
    if sha:
        # The 64-hex sha256 IS the capability: you can only verify a document
        # whose hash you already hold (unguessable), so this is safe to serve
        # publicly. When a tenant context is present we still scope to it.
        # tenant-isolation-allow: public-hash-verify-sha256-is-capability-scoped-to-request-school-when-present
        qs = ReportDocumentHash.objects.filter(sha256_hash=sha)
        if school is not None:
            qs = qs.filter(report_card__school=school)
        row = qs.select_related("report_card").first()
    elif report_card_id.isdigit():
        # report_card_id is sequential/enumerable — REQUIRE tenant scope so it can
        # never walk another tenant's reports (IDOR). No tenant context → refuse.
        if school is None:
            return JsonResponse(
                {"verified": False, "error": "Provide hash"}, status=400
            )
        row = (
            # tenant-isolation-allow: enumerable-report-card-id-scoped-to-request-school
            ReportDocumentHash.objects.filter(
                report_card_id=int(report_card_id),
                report_card__school=school,
            )
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
@audit_pii_view(model_name="ReportCard", object_id_kwarg="student_id", sensitivity="HIGH", reason="Parent annual report CSV download")
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
            financial_clearance_block_message(student, year)
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
            financial_clearance_block_message(student, year)
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
            from apps.schoolops.email_delivery import send_transactional

            # send_transactional never raises; it returns {"ok": .., "queued": ..}.
            # Report the REAL outcome — claiming success on a failed/undelivered
            # send (e.g. SMTP creds unset) leaves the parent expecting an email
            # that never arrives and the copyable link ignored.
            result = send_transactional(
                subject=subject,
                body=body,
                to=[request.user.email],
                priority="transactional",
            )
            if result.get("ok") or result.get("queued"):
                messages.success(request, "Share link emailed successfully.")
            else:
                messages.error(
                    request,
                    "We couldn't send the email just now. Please try again, or "
                    "copy the share link below.",
                )

    enable_whatsapp_share = get_effective_config(
        key="enable_whatsapp_parent_portal", request=request, default=False
    )
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
    if not get_effective_config(key="enable_parent_portal", request=request):
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
            financial_clearance_block_message(student, year)
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


@require_permission("reports.manage")
def publish_term_results(request: HttpRequest):
    school = _report_scope_school(request)
    year, active_term = _active_year_and_term_for_school(school)
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    year_id = request.GET.get("year") or request.POST.get("year") or str(year.id)
    term_id = request.GET.get("term") or request.POST.get("term") or str(active_term.id)
# tenant-isolation-allow: view-scoped-via-request-school

    year_queryset = AcademicYear.objects.filter(id=year_id)
    if school is not None:
        year_queryset = year_queryset.filter(school=school)
    else:
        year_queryset = year_queryset.filter(school__isnull=True)
    year_obj = get_object_or_404(year_queryset)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    classrooms = Classroom.objects.filter(academic_year=year_obj)
    if school is not None:
        classrooms = classrooms.filter(school=school)
    else:
        classrooms = classrooms.filter(school__isnull=True)
    classrooms = classrooms.order_by("name")

    # config-resolver-allow: namespace object passed to notify_term_results_published
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
            if school and publish_intent:
                try:
                    from apps.siteconfig.workflow_triggers import (
                        dispatch_domain_triggers_safe,
                    )

                    rp_ctx = {
                        "academic_year_id": year_obj.pk,
                        "term_id": term_obj.pk,
                        "publish_school": publish_school,
                        "classroom_ids": list(selected_classrooms),
                    }
                    dispatch_domain_triggers_safe(school, "report_published", rp_ctx)
                    dispatch_domain_triggers_safe(school, "report_generated", rp_ctx)
                except ImportError:
                    pass

                # Closed-loop: tell each affected student + results-permitted guardian
                # the moment the term is published — the milestone that gates the
                # "published" results-visibility mode. Policy-gated (off => silent),
                # on-commit, failure-isolated; never blocks the publish write.
                if publish_school or selected_classrooms:
                    try:
                        from apps.reports.notify_term_published import (
                            notify_term_results_published,
                        )

                        notify_term_results_published(
                            school=school,
                            year=year_obj,
                            term=term_obj,
                            classroom_ids=(
                                None if publish_school else list(selected_classrooms)
                            ),
                            site=site,
                        )
                    except ImportError:
                        pass
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
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "school": school,
            "years": _scoped_years_queryset(school),
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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


@require_permission("reports.manage")
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

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    year_obj = get_object_or_404(AcademicYear, id=year_id, school=school)
    terms = list(
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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


@require_permission("reports.manage")
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
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    year_obj = get_object_or_404(AcademicYear, id=year_id, school=school)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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


@login_required
def regulatory_export(request: HttpRequest):
    """
    Regulatory / MoE export: list presets (WAEC, Bulletin de Notes, Ofsted, etc.)
    and allow one-click export by preset. Staff only.
    POST: preset_id, academic_year_id?, term_id? → run build_regulatory_export and show result.
    """
    from apps.reports.moe_presets import get_moe_presets
    from apps.reports.services import build_regulatory_export

    try:
        _has_reports_manage = request.user.has_feature_permission(
            "reports.manage", school=getattr(request, "school", None)
        )
    except (AttributeError, TypeError, ValueError):
        _has_reports_manage = False

    if not (
        request.user.is_staff
        or (getattr(request.user, "role", "") or "").upper()
        in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "BURSAR")
        or _has_reports_manage
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
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            AcademicYear.objects.filter(school=school_for_years).order_by(
                "-start_date"
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            )[:20]
        )
    terms = (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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


# ---------------------------------------------------------------------------
# Bulk report-card console — generate / print / share a whole class or specialty.
#
# Single-card creation was previously a side effect of a parent clicking a
# download link; there was no way for a school to produce, print, or share a
# whole group's cards in one run, and no offline path for the schools that need
# it most. These four views are that console. All are staff-gated on the same
# ``reports.manage`` code as publish; the group axis (class vs specialty) comes
# from ``distribution_grouping`` so a technical college groups by stream and a
# base school by class without any per-school branching here.
# ---------------------------------------------------------------------------
def _bulk_scope(request: HttpRequest) -> str:
    """'annual' (whole academic year) or 'term' (default) for a bulk action."""
    raw = (request.POST.get("scope") or request.GET.get("scope") or "term").strip().lower()
    return "annual" if raw == "annual" else "term"


def _bulk_resolve_year_term(request: HttpRequest, school, *, scope: str = "term"):
    """Resolve (year_obj, term_obj) for a bulk action from GET/POST, scoped to school.

    For an ``annual`` scope ``term_obj`` is ``None`` — an annual run aggregates
    every term of the year, so no single term is selected (and a school with a
    year but no active term can still run annual once its terms are published).
    """
    year, active_term = _active_year_and_term_for_school(school)
    if not year:
        return None, None
    year_id = request.POST.get("year") or request.GET.get("year") or str(year.id)
    year_qs = AcademicYear.objects.filter(id=year_id)  # tenant-isolation-allow: view-scoped-via-request-school
    year_qs = year_qs.filter(school=school) if school is not None else year_qs.filter(school__isnull=True)
    year_obj = get_object_or_404(year_qs)
    if scope == "annual":
        return year_obj, None
    if not active_term:
        return None, None
    term_id = request.POST.get("term") or request.GET.get("term") or str(active_term.id)
    term_obj = get_object_or_404(Term, id=term_id, academic_year=year_obj)
    return year_obj, term_obj


def _bulk_console_redirect(year_obj, term_obj, scope: str = "term"):
    from django.urls import reverse

    base = reverse("reports:bulk_report_console")
    if scope == "annual" or term_obj is None:
        return redirect(f"{base}?year={year_obj.id}&scope=annual")
    return redirect(f"{base}?year={year_obj.id}&term={term_obj.id}")


@require_permission("reports.manage")
def bulk_report_console(request: HttpRequest):
    """List the term's report-card groups with generate / print / share actions."""
    from apps.reports.distribution_grouping import (
        list_report_groups,
        resolve_report_group_mode,
    )
    from apps.reports.models import ReportCardBatch

    school = _report_scope_school(request)
    scope = _bulk_scope(request)
    # Resolve the year (always) plus a display term for term-mode. Fall back to
    # annual resolution so a school with a year but no active term can still open
    # the console in annual mode.
    year_obj, term_obj = _bulk_resolve_year_term(request, school, scope="term")
    if year_obj is None:
        year_obj, _ = _bulk_resolve_year_term(request, school, scope="annual")
        if year_obj is None:
            return HttpResponseForbidden("No active academic year configured yet.")

    years = (  # tenant-isolation-allow: view-scoped-via-request-school
        AcademicYear.objects.filter(school=school)
        if school is not None
        else AcademicYear.objects.filter(school__isnull=True)
    ).order_by("-start_date")
    terms = Term.objects.filter(academic_year=year_obj).order_by("position")
    group_mode = resolve_report_group_mode(school)
    groups = list_report_groups(school, year_obj)
    recent_batches = ReportCardBatch.objects.filter(  # tenant-isolation-allow: view-scoped-via-academic-year-under-request-school
        academic_year=year_obj
    ).select_related("requested_by").order_by("-created_at")[:12]

    return render(
        request,
        "reports/bulk_console.html",
        {
            "school": school,
            "year": year_obj,
            "term": term_obj,
            "years": years,
            "terms": terms,
            "active_scope": scope,
            "is_annual": scope == "annual",
            "group_mode": group_mode,
            "group_mode_label": "Specialty" if group_mode == "SPECIALTY" else "Class",
            "groups": groups,
            "recent_batches": recent_batches,
        },
    )


@require_permission("reports.manage")
@require_http_methods(["POST"])
def bulk_report_generate(request: HttpRequest):
    """Generate (or refresh) a group's term or annual report cards in one run."""
    from apps.reports.bulk_generation import (
        generate_annual_report_cards,
        generate_term_report_cards,
    )
    from apps.reports.distribution_grouping import resolve_group
    from apps.reports.models import ReportCardBatch

    school = _report_scope_school(request)
    scope = _bulk_scope(request)
    is_annual = scope == "annual"
    year_obj, term_obj = _bulk_resolve_year_term(request, school, scope=scope)
    if year_obj is None:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    mode = request.POST.get("group_mode") or ""
    ref_id = request.POST.get("group_ref_id") or ""
    classroom = specialty = None
    label = "whole year"
    ref_id_val = None
    if ref_id:
        _ref, group_scope, label = resolve_group(school, year_obj, mode, ref_id)
        if group_scope is None:
            messages.error(request, "That class/specialty could not be found for this year.")
            return _bulk_console_redirect(year_obj, term_obj, scope)
        classroom, specialty = group_scope.get("classroom"), group_scope.get("specialty")
        ref_id_val = int(ref_id)

    if is_annual:
        result = generate_annual_report_cards(
            school=school,
            academic_year=year_obj,
            classroom=classroom,
            specialty=specialty,
            actor=request.user,
        )
    else:
        result = generate_term_report_cards(
            school=school,
            academic_year=year_obj,
            term=term_obj,
            classroom=classroom,
            specialty=specialty,
            actor=request.user,
        )
    ReportCardBatch.objects.create(
        school=school,
        academic_year=year_obj,
        term=term_obj,
        action=ReportCardBatch.Action.GENERATE,
        status=ReportCardBatch.Status.COMPLETED,
        group_mode=mode,
        group_ref_id=ref_id_val,
        group_label=(f"{label} (annual)" if is_annual else label),
        included_count=result.generated,
        skipped_count=result.skipped,
        summary=result.as_dict(),
        requested_by=request.user,
        completed_at=timezone.now(),
    )
    scope_word = "annual" if is_annual else "term"
    messages.success(
        request,
        f"Generated {result.generated} {scope_word} report card(s) for {label}"
        + (f"; {result.skipped} skipped." if result.skipped else "."),
    )
    return _bulk_console_redirect(year_obj, term_obj, scope)


@require_permission("reports.manage")
def bulk_report_print(request: HttpRequest):
    """Return a merged PDF (or ZIP) of a group's term or annual report cards for printing."""
    from apps.reports.bulk_print import build_group_report_pdf, build_group_report_zip
    from apps.reports.distribution_grouping import resolve_group, scoped_student_queryset
    from apps.reports.models import ReportCard, ReportCardBatch

    school = _report_scope_school(request)
    scope = _bulk_scope(request)
    is_annual = scope == "annual"
    report_type = ReportCard.Type.ANNUAL if is_annual else ReportCard.Type.TERM
    year_obj, term_obj = _bulk_resolve_year_term(request, school, scope=scope)
    if year_obj is None:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    mode = request.GET.get("group_mode") or request.POST.get("group_mode") or ""
    ref_id = request.GET.get("group_ref_id") or request.POST.get("group_ref_id") or ""
    fmt = (request.GET.get("format") or request.POST.get("format") or "pdf").strip().lower()

    classroom = specialty = None
    label = "whole-year"
    ref_id_val = None
    if ref_id:
        _ref, group_scope, label = resolve_group(school, year_obj, mode, ref_id)
        if group_scope is None:
            return HttpResponseForbidden("That class/specialty could not be found for this year.")
        classroom, specialty = group_scope.get("classroom"), group_scope.get("specialty")
        ref_id_val = int(ref_id)

    students = scoped_student_queryset(
        school, year_obj, classroom=classroom, specialty=specialty
    )
    if fmt == "zip":
        data, res = build_group_report_zip(
            school=school, students=students, academic_year=year_obj,
            term=term_obj, report_type=report_type, actor=request.user,
        )
        content_type, ext = "application/zip", "zip"
    else:
        data, res = build_group_report_pdf(
            school=school, students=students, academic_year=year_obj,
            term=term_obj, report_type=report_type, actor=request.user,
        )
        content_type, ext = "application/pdf", "pdf"

    ReportCardBatch.objects.create(
        school=school,
        academic_year=year_obj,
        term=term_obj,
        action=ReportCardBatch.Action.PRINT,
        status=ReportCardBatch.Status.COMPLETED,
        group_mode=mode,
        group_ref_id=ref_id_val,
        group_label=(f"{label} (annual)" if is_annual else label),
        included_count=res.included,
        skipped_count=res.skipped,
        summary={"reasons": res.reasons, "format": ext, "scope": scope},
        requested_by=request.user,
        completed_at=timezone.now(),
    )

    if not data:
        messages.warning(request, "No eligible report cards to print for this group yet — generate them first.")
        return _bulk_console_redirect(year_obj, term_obj, scope)

    safe_label = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(label))[:60]
    scope_tag = "annual" if is_annual else f"t{term_obj.id}"
    resp = HttpResponse(data, content_type=content_type)
    resp["Content-Disposition"] = (
        f'attachment; filename="report-cards-{safe_label}-{scope_tag}.{ext}"'
    )
    return resp


@require_permission("reports.manage")
@require_http_methods(["POST"])
def bulk_report_share(request: HttpRequest):
    """Queue a group's report cards to be shared with families (offline-first)."""
    from apps.platform_runtime.offline_action_types import OfflineActionType
    from apps.platform_runtime.offline_queue import (
        enqueue_offline_action,
        process_offline_queue,
    )
    from apps.reports.distribution_grouping import resolve_group
    from apps.reports.models import ReportCardBatch

    school = _report_scope_school(request)
    scope = _bulk_scope(request)
    is_annual = scope == "annual"
    year_obj, term_obj = _bulk_resolve_year_term(request, school, scope=scope)
    if year_obj is None:
        return HttpResponseForbidden("No active academic year/term configured yet.")
    if school is None:
        # The offline queue is tenant-bound (OfflineAction.school is required); a
        # school-less shared context has no tenant to queue against.
        return HttpResponseForbidden("Sharing requires a tenant school context.")

    mode = request.POST.get("group_mode") or ""
    ref_id = request.POST.get("group_ref_id") or ""
    label = "whole year"
    ref_id_val = None
    if ref_id:
        _ref, group_scope, label = resolve_group(school, year_obj, mode, ref_id)
        if group_scope is None:
            messages.error(request, "That class/specialty could not be found for this year.")
            return _bulk_console_redirect(year_obj, term_obj, scope)
        ref_id_val = int(ref_id)

    batch = ReportCardBatch.objects.create(
        school=school,
        academic_year=year_obj,
        term=term_obj,
        action=ReportCardBatch.Action.SHARE,
        status=ReportCardBatch.Status.QUEUED,
        group_mode=mode,
        group_ref_id=ref_id_val,
        group_label=(f"{label} (annual)" if is_annual else label),
        requested_by=request.user,
    )
    enqueue_offline_action(
        user_id=request.user.id,
        school_id=school.id,
        action_type=OfflineActionType.REPORT_BATCH_DISTRIBUTE,
        payload={
            "academic_year_id": year_obj.id,
            "term_id": term_obj.id if term_obj is not None else None,
            "group_mode": mode,
            "group_ref_id": ref_id_val,
            "batch_id": batch.id,
            "report_type": "ANNUAL" if is_annual else "TERM",
        },
        idempotency_key=f"rcbatch-{batch.id}",
    )
    # Local-first: the durable queue row is the anchor. Drain it now so a cloud
    # tenant shares immediately; an offline edge box keeps it QUEUED to send on
    # its next sync. The queue's own status machine prevents double-processing.
    try:
        process_offline_queue(school_id=school.id, user_id=request.user.id, limit=5)
        batch.refresh_from_db()
    except (DatabaseError, ValueError, RuntimeError):
        pass

    scope_word = "annual" if is_annual else "term"
    if batch.status == ReportCardBatch.Status.COMPLETED:
        messages.success(
            request,
            f"Shared {label} {scope_word} report cards with {batch.included_count} family group(s).",
        )
    else:
        messages.success(
            request,
            f"Queued {label} {scope_word} report cards to share. They will be sent as soon as this device is back online.",
        )
    return _bulk_console_redirect(year_obj, term_obj, scope)
