"""Bundle a whole group's report cards into one artifact for printing/handout.

Generating cards one-per-student (``bulk_generation``) gave schools the cards;
it did not give them a way to *print a class in one go*. A head teacher does not
open 32 download links — they want a single PDF to send to the printer, or a ZIP
to file. This module is that missing verb, and it is deliberately
NON-destructive: it reuses the immutable frozen archive bytes for any card that
was already published, and renders the rest on the fly WITHOUT persisting, so
printing never mutates the ledger or re-freezes a card.

The group (a class or a specialty) and its student set come from
``distribution_grouping`` so print covers exactly what generate and share do.
Eligibility (published / fee-cleared / has-marks) is the same gate as
generation, so an unpublished or fee-blocked card is never printed by the back
door.
"""
from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field

from django.db import DatabaseError

from apps.reports.models import ReportCard

logger = logging.getLogger(__name__)


@dataclass
class GroupPrintResult:
    """Outcome of a bulk print/bundle run — what went in, what was skipped, why."""

    included: int = 0
    skipped: int = 0
    student_ids: list[int] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)

    def _skip(self, reason: str) -> None:
        self.skipped += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def _include(self, student_id) -> None:
        self.included += 1
        if student_id is not None:
            self.student_ids.append(student_id)


def _default_pdf_renderer(request, template_name, context):
    from apps.reports.weasy import render_pdf_bytes

    return render_pdf_bytes(request, template_name, context)


def _student_term_pdf_bytes(
    *, request, student, academic_year, term, render_pdf, enforce_publish, enforce_fee_clearance
) -> tuple[bytes | None, str]:
    """One student's TERM card as PDF bytes for the bundle, or (None, reason).

    Prefers the frozen archive bytes (already gate-cleared at generation); falls
    back to an ephemeral render for a not-yet-generated card, applying the exact
    same eligibility gate as generation so nothing slips out unpublished.
    """
    from apps.reports.bulk_generation import (
        SKIP_NO_MARKS,
        SKIP_RENDER_FAILED,
        render_term_report_pdf_bytes,
        student_report_eligibility,
    )
    from apps.reports.services import term_report_context
    from apps.reports.views import _frozen_pdf_bytes, _report_card_is_frozen

    existing_rc = ReportCard.objects.filter(
        academic_year=academic_year,
        term=term,
        student=student,
        type=ReportCard.Type.TERM,
    ).first()
    # A frozen (published) card is the authoritative artifact — reuse its exact
    # bytes so the printed stack matches what a parent downloads to the byte.
    if existing_rc is not None and _report_card_is_frozen(existing_rc):
        frozen = _frozen_pdf_bytes(existing_rc)
        if frozen:
            return frozen, ""

    ok, reason, _note = student_report_eligibility(
        student,
        academic_year,
        term,
        enforce_publish=enforce_publish,
        enforce_fee_clearance=enforce_fee_clearance,
    )
    if not ok:
        return None, reason

    try:
        context = term_report_context(student, academic_year, term)
        if not (context.get("rows") or []):
            return None, SKIP_NO_MARKS
        pdf_bytes = render_term_report_pdf_bytes(
            request=request,
            student=student,
            academic_year=academic_year,
            term=term,
            context=context,
            render_pdf=render_pdf,
        )
        return pdf_bytes, ""
    except (DatabaseError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
        logger.warning(
            "bulk print render failed for student=%s: %s",
            getattr(student, "id", None),
            exc,
        )
        return None, SKIP_RENDER_FAILED


def _iter_group_pdfs(
    *, school, students, academic_year, term, actor, render_pdf, enforce_publish, enforce_fee_clearance
):
    """Yield ``(student, pdf_bytes_or_None, reason)`` for each student in a group."""
    from apps.reports.bulk_generation import _synthetic_request

    request = _synthetic_request(school, actor=actor)
    for student in students:
        pdf_bytes, reason = _student_term_pdf_bytes(
            request=request,
            student=student,
            academic_year=academic_year,
            term=term,
            render_pdf=render_pdf,
            enforce_publish=enforce_publish,
            enforce_fee_clearance=enforce_fee_clearance,
        )
        yield student, pdf_bytes, reason


def build_group_report_pdf(
    *,
    school,
    students,
    academic_year,
    term,
    actor=None,
    render_pdf=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
) -> tuple[bytes, GroupPrintResult]:
    """Merge a group's TERM cards into one print-ready PDF (one card per page-run).

    Returns ``(pdf_bytes, GroupPrintResult)``. ``pdf_bytes`` is empty when no
    student in the group is eligible — the caller decides how to surface that.
    """
    from pypdf import PdfReader, PdfWriter

    render_pdf = render_pdf or _default_pdf_renderer
    result = GroupPrintResult()
    writer = PdfWriter()

    for student, pdf_bytes, reason in _iter_group_pdfs(
        school=school,
        students=students,
        academic_year=academic_year,
        term=term,
        actor=actor,
        render_pdf=render_pdf,
        enforce_publish=enforce_publish,
        enforce_fee_clearance=enforce_fee_clearance,
    ):
        if not pdf_bytes:
            result._skip(reason)
            continue
        try:
            writer.append(PdfReader(io.BytesIO(pdf_bytes)))
            result._include(getattr(student, "id", None))
        except Exception as exc:  # noqa: BLE001 — a single unreadable PDF must not abort the batch
            from apps.reports.bulk_generation import SKIP_RENDER_FAILED

            logger.warning(
                "bulk print merge failed for student=%s: %s",
                getattr(student, "id", None),
                exc,
            )
            result._skip(SKIP_RENDER_FAILED)

    if result.included == 0:
        return b"", result

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), result


def build_group_report_zip(
    *,
    school,
    students,
    academic_year,
    term,
    actor=None,
    render_pdf=None,
    enforce_publish: bool = True,
    enforce_fee_clearance: bool = True,
) -> tuple[bytes, GroupPrintResult]:
    """Bundle a group's TERM cards as a ZIP of one PDF per student.

    Returns ``(zip_bytes, GroupPrintResult)``; ``zip_bytes`` is empty when no
    student is eligible.
    """
    render_pdf = render_pdf or _default_pdf_renderer
    result = GroupPrintResult()
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for student, pdf_bytes, reason in _iter_group_pdfs(
            school=school,
            students=students,
            academic_year=academic_year,
            term=term,
            actor=actor,
            render_pdf=render_pdf,
            enforce_publish=enforce_publish,
            enforce_fee_clearance=enforce_fee_clearance,
        ):
            if not pdf_bytes:
                result._skip(reason)
                continue
            code = str(getattr(student, "student_code", "") or "").strip()
            stem = code or f"student-{getattr(student, 'id', 'x')}"
            zf.writestr(f"report-{stem}.pdf", pdf_bytes)
            result._include(getattr(student, "id", None))

    if result.included == 0:
        return b"", result
    return buf.getvalue(), result
