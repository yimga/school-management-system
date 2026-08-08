"""Produce a whole class's (or term's) report cards in one run.

Until now a ``ReportCard`` row could only come into existence as a side effect of
a PARENT hitting the download URL — the only three creation sites are the two
``parent_download_*`` views and the e2e seed helper. There is no management
command, no service, no Celery task. A seeded 200-student Buea term therefore
had **3 report cards for 200 students**: one per parent who happened to click.

That is not a reporting gap, it is an operational one. A school cannot produce
report cards for a class at all, and the students least likely to have a parent
with a smartphone and data are exactly the ones who end up with no record.

This module gives the school the missing verb, reusing the view's own pipeline so
a bulk-generated card is byte-identical in shape to a parent-downloaded one:
same ``term_report_context``, same style resolution, same QR, same
``ReportDocumentHash`` ledger entry, same ``school`` stamping (a NULL there makes
tenant-scoped QR verification 404).

Gates are honoured by default and each skip is REPORTED with its reason, so
running this doubles as an audit of who cannot receive a report card and why.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.db import DatabaseError, transaction
from django.test import RequestFactory

from apps.reports.models import ReportCard

logger = logging.getLogger(__name__)

# Skip reasons — stable keys so callers/tests can assert on them.
SKIP_NOT_PUBLISHED = "not_published"
SKIP_NO_MARKS = "no_marks"
SKIP_FEE_BLOCKED = "fee_blocked"
SKIP_OUTSTANDING_RETURNS = "outstanding_returns"
SKIP_THIRD_TERM_BLOCKED = "third_term_blocked"
SKIP_RENDER_FAILED = "render_failed"


@dataclass
class BulkReportResult:
    generated: int = 0
    skipped: int = 0
    students: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    details: list[dict] = field(default_factory=list)

    def _skip(self, student, reason: str, note: str = "") -> None:
        self.skipped += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1
        self.details.append(
            {
                "student_id": getattr(student, "id", None),
                "student_code": getattr(student, "student_code", "") or "",
                "status": "skipped",
                "reason": reason,
                "note": note,
            }
        )

    def _ok(self, student, created: bool) -> None:
        self.generated += 1
        self.details.append(
            {
                "student_id": getattr(student, "id", None),
                "student_code": getattr(student, "student_code", "") or "",
                "status": "created" if created else "updated",
                "reason": "",
                "note": "",
            }
        )

    def as_dict(self) -> dict:
        return {
            "students": self.students,
            "generated": self.generated,
            "skipped": self.skipped,
            "reasons": dict(self.reasons),
            "details": self.details,
        }


def student_report_eligibility(
    student,
    academic_year,
    term,
    *,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
) -> tuple[bool, str, str]:
    """Whether one student's TERM card may be produced, and why not.

    The gate order + reasons are the contract bulk generate AND bulk print/share
    share, so a card refused generation is never quietly printed or shared
    instead. Returns ``(ok, reason_key, note)`` — ``reason_key`` is one of the
    ``SKIP_*`` constants (empty when ``ok``); ``note`` carries the human fee
    message when relevant. The "no marks" check stays with the caller because it
    needs the built report context.
    """
    from apps.reports.services import (
        financial_clearance_block_message,
        is_term_published,
        student_has_financial_clearance,
        student_has_outstanding_returns,
    )

    if enforce_publish and not is_term_published(
        academic_year.id, term.id, getattr(student, "classroom_id", None)
    ):
        return False, SKIP_NOT_PUBLISHED, ""

    # Third-term rule: some classrooms (Form 5 / Upper Sixth) stop at two.
    classroom_obj = getattr(student, "classroom", None)
    if (
        getattr(term, "position", None) == 3
        and classroom_obj is not None
        and not getattr(classroom_obj, "allows_third_term", True)
    ):
        return False, SKIP_THIRD_TERM_BLOCKED, ""

    if enforce_fee_clearance and not student_has_financial_clearance(
        student, academic_year
    ):
        return (
            False,
            SKIP_FEE_BLOCKED,
            financial_clearance_block_message(student, academic_year),
        )

    if student_has_outstanding_returns(student, academic_year):
        return False, SKIP_OUTSTANDING_RETURNS, ""

    return True, "", ""


def _synthetic_request(school, actor=None):
    """A request good enough for absolute-URI building and tenant scoping.

    The render + QR helpers are written against a request (``build_absolute_uri``
    for WeasyPrint's base_url, ``request.school`` for tenant-scoped verification).
    A management command has none, so synthesise one rather than fork the
    pipeline — forking is how bulk output drifts from what parents actually get.
    """
    request = RequestFactory().get("/")
    request.school = school
    if actor is not None:
        request.user = actor
    return request


def _default_pdf_renderer(request, template_name, context):
    from apps.reports.weasy import render_pdf_bytes

    return render_pdf_bytes(request, template_name, context)


def annual_report_eligibility(
    student,
    academic_year,
    *,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
) -> tuple[bool, str, str]:
    """Whether one student's ANNUAL (end-of-year) card may be produced, and why not.

    The annual card aggregates every term of the year, so it needs ALL of that
    student's terms published (``are_terms_published``) — not just one. The
    third-term rule is already handled inside ``terms_for_student`` (Form 5 /
    Upper Sixth stop at two), so it is not re-checked here. Fee-clearance and
    outstanding-returns gates are identical to the term card. Returns
    ``(ok, reason_key, note)`` using the same ``SKIP_*`` contract as
    :func:`student_report_eligibility` so a card refused generation is never
    quietly printed or shared instead.
    """
    from apps.reports.services import (
        are_terms_published,
        financial_clearance_block_message,
        student_has_financial_clearance,
        student_has_outstanding_returns,
        terms_for_student,
    )

    classroom_obj = getattr(student, "classroom", None)
    if classroom_obj is None:
        # No classroom → no terms to aggregate; treat as not-yet-ready rather
        # than raising, so one unplaced student never aborts the batch.
        return False, SKIP_NOT_PUBLISHED, ""

    terms = terms_for_student(academic_year, classroom_obj)
    if enforce_publish and not are_terms_published(
        academic_year.id,
        [t.id for t in terms],
        getattr(student, "classroom_id", None),
    ):
        return False, SKIP_NOT_PUBLISHED, ""

    if enforce_fee_clearance and not student_has_financial_clearance(
        student, academic_year
    ):
        return (
            False,
            SKIP_FEE_BLOCKED,
            financial_clearance_block_message(student, academic_year),
        )

    if student_has_outstanding_returns(student, academic_year):
        return False, SKIP_OUTSTANDING_RETURNS, ""

    return True, "", ""


def build_annual_bulk_context(student, academic_year) -> dict:
    """The annual render context, matching the parent single-card annual download.

    Reuses the production ``annual_report_context`` (the same cross-term
    aggregation, ranking and promotion the parent download renders) and adds the
    student/year/generated_at keys the annual template expects — so a bulk-run
    annual card is byte-shaped identically to a parent-downloaded one.
    """
    from django.utils import timezone

    from apps.reports.services import annual_report_context

    context = annual_report_context(student, academic_year)
    context.update(
        {
            "student": student,
            "student_name": f"{student.last_name} {student.first_name}",
            "year": academic_year,
            "generated_at": timezone.now(),
        }
    )
    return context


def _bulk_report_context(student, academic_year, term, report_type):
    """Build one card's render context — term or annual — via the shared builders."""
    if report_type == ReportCard.Type.ANNUAL:
        return build_annual_bulk_context(student, academic_year)
    from apps.reports.services import term_report_context

    return term_report_context(student, academic_year, term)


def _context_has_marks(context, report_type) -> bool:
    """False for an un-assessed student, so a blank crest-only sheet is skipped."""
    if report_type == ReportCard.Type.ANNUAL:
        # No computed annual average means no marks across any term.
        return context.get("annual_average") is not None
    return bool(context.get("rows") or [])


def _generate_report_cards(
    *,
    school,
    academic_year,
    report_type,
    term=None,
    classroom=None,
    specialty=None,
    actor=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
    dry_run: bool = False,
    pdf_renderer=None,
) -> BulkReportResult:
    """Generate (or refresh) TERM or ANNUAL report cards for a group — one shared loop.

    ``report_type`` is ``ReportCard.Type.TERM`` (needs ``term``) or
    ``ReportCard.Type.ANNUAL`` (aggregates every published term; ``term`` is
    ``None``). Pass ``classroom`` to narrow to one class, ``specialty`` to narrow
    to one stream, or neither for the whole year. The scoping (including the
    ``school__isnull=True`` rule that stops a bare ``school=`` filter dropping
    almost the entire roll) lives in
    :func:`apps.reports.distribution_grouping.scoped_student_queryset` so bulk
    generate / print / share always cover the identical set of students.

    Returns a :class:`BulkReportResult`; nothing raises for a single student's
    failure — one bad row must not abandon the other 199.
    """
    from apps.reports.distribution_grouping import scoped_student_queryset

    is_annual = report_type == ReportCard.Type.ANNUAL
    render_pdf = pdf_renderer or _default_pdf_renderer
    result = BulkReportResult()

    students = scoped_student_queryset(
        school, academic_year, classroom=classroom, specialty=specialty
    )

    request = _synthetic_request(school, actor=actor)

    for student in students:
        result.students += 1
        try:
            if is_annual:
                ok, reason, note = annual_report_eligibility(
                    student,
                    academic_year,
                    enforce_publish=enforce_publish,
                    enforce_fee_clearance=enforce_fee_clearance,
                )
            else:
                ok, reason, note = student_report_eligibility(
                    student,
                    academic_year,
                    term,
                    enforce_publish=enforce_publish,
                    enforce_fee_clearance=enforce_fee_clearance,
                )
            if not ok:
                result._skip(student, reason, note)
                continue

            context = _bulk_report_context(student, academic_year, term, report_type)
            if not _context_has_marks(context, report_type):
                # A card with no subjects/marks is a blank sheet with a school
                # crest; generating it would misrepresent an un-assessed student.
                result._skip(student, SKIP_NO_MARKS)
                continue

            if dry_run:
                result._ok(student, created=True)
                continue

            _persist_one(
                request=request,
                school=school,
                student=student,
                academic_year=academic_year,
                term=term,
                report_type=report_type,
                context=context,
                actor=actor,
                render_pdf=render_pdf,
                result=result,
            )
        except (DatabaseError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
            logger.warning(
                "bulk report card failed for student=%s: %s",
                getattr(student, "id", None),
                exc,
            )
            result._skip(student, SKIP_RENDER_FAILED, f"{type(exc).__name__}: {exc}"[:200])

    return result


def generate_term_report_cards(
    *,
    school,
    academic_year,
    term,
    classroom=None,
    specialty=None,
    actor=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
    dry_run: bool = False,
    pdf_renderer=None,
) -> BulkReportResult:
    """Generate (or refresh) TERM report cards for a classroom, a specialty, or the whole year."""
    return _generate_report_cards(
        school=school,
        academic_year=academic_year,
        report_type=ReportCard.Type.TERM,
        term=term,
        classroom=classroom,
        specialty=specialty,
        actor=actor,
        enforce_publish=enforce_publish,
        enforce_fee_clearance=enforce_fee_clearance,
        dry_run=dry_run,
        pdf_renderer=pdf_renderer,
    )


def generate_annual_report_cards(
    *,
    school,
    academic_year,
    classroom=None,
    specialty=None,
    actor=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
    dry_run: bool = False,
    pdf_renderer=None,
) -> BulkReportResult:
    """Generate (or refresh) ANNUAL (end-of-year) report cards for a group.

    Requires every term of the year published; a mid-year run therefore skips
    most students with ``not_published`` — expected, and the skip breakdown is
    the audit of who is not yet ready for an annual transcript.
    """
    return _generate_report_cards(
        school=school,
        academic_year=academic_year,
        report_type=ReportCard.Type.ANNUAL,
        term=None,
        classroom=classroom,
        specialty=specialty,
        actor=actor,
        enforce_publish=enforce_publish,
        enforce_fee_clearance=enforce_fee_clearance,
        dry_run=dry_run,
        pdf_renderer=pdf_renderer,
    )


def render_term_report_pdf_bytes(
    *, request, student, academic_year, term, context, render_pdf
) -> bytes:
    """Render one TERM card to PDF bytes — the shared render, no persistence.

    Adds the verification QR + share URL and resolves the per-student style
    template exactly as the parent download and bulk generation do, so a card
    that is generated, printed and shared is byte-shaped identically. Callers
    that persist (bulk generation) hash the returned bytes; callers that only
    print/bundle (bulk print) use them ephemerally.
    """
    from apps.reports.services import (
        build_share_token,
        build_share_url,
        generate_report_qr_code,
    )
    from apps.siteconfig.models_tooling import get_report_card_style_for_student

    token = build_share_token("TERM", student.id, academic_year.id, term.id)
    context = dict(context)
    context["qr_code_data_uri"] = generate_report_qr_code(
        build_share_url(request, token)
    )
    context["verification_url"] = build_share_url(request, token)

    template_name = "reports/term_report.html"
    try:
        style = get_report_card_style_for_student(student, ReportCard.Type.TERM)
        if style is not None:
            template_name = style.template_for(ReportCard.Type.TERM) or template_name
    except (DatabaseError, AttributeError, ValueError, TypeError):
        pass

    return render_pdf(request, template_name, context)


def render_annual_report_pdf_bytes(
    *, request, student, academic_year, context, render_pdf
) -> bytes:
    """Render one ANNUAL card to PDF bytes — the shared render, no persistence.

    The annual sibling of :func:`render_term_report_pdf_bytes`: same QR + share
    URL + per-student style resolution the parent single-card annual download
    uses, so a bulk-generated annual card is byte-shaped identically. The share
    token is annual-typed (``term`` is ``None``) and the template defaults to
    ``reports/annual_report.html`` unless the student's style overrides it.
    """
    from apps.reports.services import (
        build_share_token,
        build_share_url,
        generate_report_qr_code,
    )
    from apps.siteconfig.models_tooling import get_report_card_style_for_student

    token = build_share_token("annual", student.id, academic_year.id, None)
    context = dict(context)
    context["qr_code_data_uri"] = generate_report_qr_code(
        build_share_url(request, token)
    )
    context["verification_url"] = build_share_url(request, token)

    template_name = "reports/annual_report.html"
    try:
        style = get_report_card_style_for_student(student, ReportCard.Type.ANNUAL)
        if style is not None:
            template_name = style.template_for(ReportCard.Type.ANNUAL) or template_name
    except (DatabaseError, AttributeError, ValueError, TypeError):
        pass

    return render_pdf(request, template_name, context)


def _persist_one(
    *,
    request,
    school,
    student,
    academic_year,
    term,
    report_type,
    context,
    actor,
    render_pdf,
    result,
):
    """Render + persist one card (term or annual), mirroring the parent download."""
    from apps.reports.views import _record_report_hash, _report_card_is_frozen

    is_annual = report_type == ReportCard.Type.ANNUAL
    # Annual cards are keyed with ``term=None`` (one per year); term cards per term.
    lookup = {
        "academic_year": academic_year,
        "student": student,
        "type": report_type,
        "term": None if is_annual else term,
    }

    # Immutable archive: a report card that was already published (frozen — its
    # verification hash is recorded) must not be silently re-rendered or
    # overwritten by a bulk run. A deliberate reissue is a separate, explicit
    # action; bulk generation leaves frozen cards untouched.
    # tenant-isolation-allow: report-card-scoped-via-school-owned-academic-year-and-student
    existing_rc = ReportCard.objects.filter(**lookup).first()
    if existing_rc is not None and _report_card_is_frozen(existing_rc):
        result._ok(student, False)
        return

    if is_annual:
        pdf_bytes = render_annual_report_pdf_bytes(
            request=request,
            student=student,
            academic_year=academic_year,
            context=context,
            render_pdf=render_pdf,
        )
        filename = f"annual-report-{student.id}.pdf"
    else:
        pdf_bytes = render_term_report_pdf_bytes(
            request=request,
            student=student,
            academic_year=academic_year,
            term=term,
            context=context,
            render_pdf=render_pdf,
        )
        filename = f"report-{student.id}-{term.id}.pdf"

    # student.school is the authoritative owner; fall back to the run's school so
    # the row is never left NULL — a NULL school makes tenant-scoped QR/hash
    # verification 404 for every tenant.
    owner = getattr(student, "school", None) or school

    with transaction.atomic():
        report_card, created = ReportCard.objects.get_or_create(
            **lookup,
            defaults={"school": owner},
        )
        if report_card.school_id is None and owner is not None:
            report_card.school = owner
        report_card.pdf_file.save(
            filename,
            ContentFile(pdf_bytes),
            save=True,
        )
        _record_report_hash(actor, report_card, pdf_bytes)

    result._ok(student, created)
