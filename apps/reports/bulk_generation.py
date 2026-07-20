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
from django.db.models import Q
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


def generate_term_report_cards(
    *,
    school,
    academic_year,
    term,
    classroom=None,
    actor=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
    dry_run: bool = False,
    pdf_renderer=None,
) -> BulkReportResult:
    """Generate (or refresh) TERM report cards for a classroom, or the whole year.

    Returns a :class:`BulkReportResult`; nothing raises for a single student's
    failure — one bad row must not abandon the other 199.
    """
    from apps.people.models import StudentProfile
    from apps.reports.services import (
        financial_clearance_block_message,
        is_term_published,
        student_has_financial_clearance,
        student_has_outstanding_returns,
        term_report_context,
    )

    render_pdf = pdf_renderer or _default_pdf_renderer
    result = BulkReportResult()

    students = StudentProfile.objects.filter(  # tenant-isolation-allow: bulk-report-scoped-via-caller-school-and-academic-year
        academic_year=academic_year, is_active=True
    )
    if school is not None:
        # Include school__isnull=True. Under schema-per-tenant the per-row FK is
        # redundant (the schema already isolates the tenant) and is very often
        # NULL — the platform's own seeders leave it unset. A bare
        # filter(school=school) therefore silently drops almost the entire roll:
        # on the Buea tenant it matched 1 student of 20, which would have looked
        # like "the class only has one student" rather than a scoping bug. The
        # academic_year + tenant schema already bound this queryset.
        students = students.filter(Q(school=school) | Q(school__isnull=True))
    if classroom is not None:
        students = students.filter(classroom=classroom)
    students = students.select_related("classroom", "specialty", "school").order_by(
        "last_name", "first_name"
    )

    request = _synthetic_request(school, actor=actor)

    for student in students:
        result.students += 1
        try:
            if enforce_publish and not is_term_published(
                academic_year.id, term.id, getattr(student, "classroom_id", None)
            ):
                result._skip(student, SKIP_NOT_PUBLISHED)
                continue

            # Third-term rule: some classrooms (Form 5 / Upper Sixth) stop at two.
            classroom_obj = getattr(student, "classroom", None)
            if (
                getattr(term, "position", None) == 3
                and classroom_obj is not None
                and not getattr(classroom_obj, "allows_third_term", True)
            ):
                result._skip(student, SKIP_THIRD_TERM_BLOCKED)
                continue

            if enforce_fee_clearance and not student_has_financial_clearance(
                student, academic_year
            ):
                result._skip(
                    student,
                    SKIP_FEE_BLOCKED,
                    financial_clearance_block_message(student, academic_year),
                )
                continue

            if student_has_outstanding_returns(student, academic_year):
                result._skip(student, SKIP_OUTSTANDING_RETURNS)
                continue

            context = term_report_context(student, academic_year, term)
            if not (context.get("rows") or []):
                # A card with no subjects is a blank sheet with a school crest;
                # generating it would misrepresent an un-assessed student.
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


def _persist_one(
    *, request, school, student, academic_year, term, context, actor, render_pdf, result
):
    """Render + persist one card, mirroring parent_download_term_report."""
    from apps.reports.services import (
        build_share_token,
        build_share_url,
        generate_report_qr_code,
    )
    from apps.reports.views import _record_report_hash
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

    pdf_bytes = render_pdf(request, template_name, context)

    # student.school is the authoritative owner; fall back to the run's school so
    # the row is never left NULL — a NULL school makes tenant-scoped QR/hash
    # verification 404 for every tenant.
    owner = getattr(student, "school", None) or school

    with transaction.atomic():
        report_card, created = ReportCard.objects.get_or_create(
            academic_year=academic_year,
            term=term,
            student=student,
            type=ReportCard.Type.TERM,
            defaults={"school": owner},
        )
        if report_card.school_id is None and owner is not None:
            report_card.school = owner
        report_card.pdf_file.save(
            f"report-{student.id}-{term.id}.pdf",
            ContentFile(pdf_bytes),
            save=True,
        )
        _record_report_hash(actor, report_card, pdf_bytes)

    result._ok(student, created)
