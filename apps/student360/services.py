"""
Student 360: timeline feed, aggregation summary, permission-gated export pack,
and immutable transcript + cross-year archive (Section 15.1).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

from apps.platform_runtime.structured_logging import log_exception_with_context

# Typed exception set for optional 360 data (queries, imports, serialization).
_STUDENT360_SERVICE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    LookupError,
    ObjectDoesNotExist,
    KeyError,
    DatabaseError,
)


def app_installed(label: str) -> bool:
    """Whether an app with this LABEL (e.g. ``"finance"``) is installed.

    ``django.apps.apps.is_installed()`` matches the full dotted app NAME
    (``"apps.finance"``), NOT the label — so the historical ``is_installed("finance")``
    guards were ALWAYS False and silently disabled the finance / evals / attendance /
    reports sections of the 360 view. Resolve by label instead.
    """
    from django.apps import apps as _django_apps

    try:
        _django_apps.get_app_config(label)
        return True
    except LookupError:
        return False


def get_student_360_summary(
    school_id,
    student_id: int,
    *,
    include_timeline_count: bool = True,
    include_export_available: bool = True,
) -> Dict[str, Any]:
    """
    Aggregated 360 view for a student: linked academic, finance, attendance, and timeline/export pointers.
    Caller must enforce permission. Returns dict with sections and counts (no PII in keys; values are counts/summaries).
    """
    out = {
        "student_id": student_id,
        "school_id": str(school_id),
        "academic": {},
        "finance": {},
        "attendance": {},
        "behavior": {},
        "safeguarding": {},
    }
    try:
        from django.apps import apps

        StudentProfile = apps.get_model("people", "StudentProfile")
        student = StudentProfile.objects.filter(
            school_id=school_id, pk=student_id
        ).first()
        if not student:
            return out
        # Academic: evaluations count, enrollments
        if app_installed("evals"):
            Evaluation = apps.get_model("evals", "Evaluation")
            # tenant-isolation-allow: `student` already school-scoped on line 52 (reviewed 2026-05-14)
            out["academic"]["evaluations_count"] = Evaluation.objects.filter(
                student=student
            ).count()
        # Real per-year enrollment history (program item 2.2). This used to be
        # hardcoded to `1 if student.classroom_id else 0` because the placement
        # was a single FK on the profile and no historical model existed, so a
        # student who had been at the school for five years reported one
        # enrollment. Falls back to that shim only when the backfill has not
        # reached this tenant yet.
        enrollments_count = student.enrollments.count()
        out["academic"]["enrollments_count"] = enrollments_count or (
            1 if getattr(student, "classroom_id", None) else 0
        )
        # Finance: invoices summary
        if app_installed("finance"):
            Invoice = apps.get_model("finance", "Invoice")
            # Exclude VOID to match the authoritative finance balance runner
            # (finance/family_billing_aggregator.py::_default_balance_runner does
            # `.exclude(status=VOID)`); a voided invoice still carries a positive
            # total_amount, so summing all statuses overstated the 360 headline.
            # tenant-isolation-allow: `student` already school-scoped on line 52 (reviewed 2026-05-14)
            inv_qs = Invoice.objects.filter(student=student).exclude(
                status=Invoice.Status.VOID
            )
            out["finance"]["invoices_count"] = inv_qs.count()
            from django.db.models import Sum

            tot = inv_qs.aggregate(s=Sum("total_amount"))
            out["finance"]["invoices_total"] = float(tot["s"] or 0)
        # Attendance: placeholder (policy-driven)
        out["attendance"]["summary_available"] = app_installed("siteconfig")
        if include_timeline_count:
            try:
                from apps.events.models import DomainEvent
                from django.db.models import Q

                out["timeline_events_count"] = (
                    DomainEvent.objects.filter(school_id=school_id)
                    .filter(
                        Q(payload__student_id=student_id)
                        | Q(payload__student_id=str(student_id))
                    )
                    .count()
                )
            except _STUDENT360_SERVICE_ERRORS:
                out["timeline_events_count"] = 0
        if include_export_available:
            out["export_pack_available"] = True
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "get_student_360_summary failed",
            school_id=school_id,
            extra={"student_id": student_id},
        )
    return out


def get_student_timeline_feed(
    school_id,
    student_id: int,
    *,
    limit: int = 100,
    event_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Unified timeline of events for a student (admissions, academic, behavior, finance, etc.).
    Reads from DomainEvent outbox where payload references this student.
    Caller must enforce permission (e.g. user can view this student).
    """
    try:
        from apps.events.models import DomainEvent
        from django.db.models import Q

        qs = (
            DomainEvent.objects.filter(school_id=school_id)
            .filter(
                Q(payload__student_id=student_id)
                | Q(payload__student_id=str(student_id))
            )
            .order_by("-created_at")[:limit]
        )
        if event_types:
            qs = qs.filter(event_type__in=event_types)
        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in qs
        ]
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "get_student_timeline_feed failed",
            school_id=school_id,
            extra={"student_id": student_id},
        )
        return []


def export_student_pack(
    school_id,
    student_id: int,
    *,
    format: str = "json",
) -> Optional[Dict[str, Any]]:
    """
    Permission-gated export pack for a student (GDPR data portability).
    Delegates to compliance.gdpr_services.export_student_data_portability.
    Caller must enforce MFA and access control before calling.
    """
    try:
        from apps.compliance.gdpr_services import export_student_data_portability

        return export_student_data_portability(school_id, student_id, format=format)
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "export_student_pack failed",
            school_id=school_id,
            extra={"student_id": student_id, "format": format},
        )
        return None


def build_transcript_snapshot(student, academic_year) -> Optional[Dict[str, Any]]:
    """
    Build a JSON-serializable transcript snapshot for one student and academic year.
    Uses reports.annual_report_context; strips model instances so the result is storable in JSONField.
    Returns None if reports/evals data is unavailable.
    """
    try:

        if not app_installed("reports"):
            return None
        from apps.reports.services import annual_report_context

        ctx = annual_report_context(student, academic_year)
        # Make JSON-serializable: replace Term objects with minimal dicts
        terms = ctx.get("terms") or []
        terms_data = [
            {
                "id": t.id,
                "label": getattr(t, "label", str(t)),
                "name": getattr(t, "name", ""),
            }
            for t in terms
        ]
        snapshot = {
            "academic_year_id": academic_year.id,
            "academic_year_name": getattr(academic_year, "name", ""),
            "student_id": student.id,
            "student_name": getattr(student, "display_name", None)
            or f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}".strip()
            or str(student),
            "term_rows": ctx.get("term_rows") or [],
            "terms": terms_data,
            "annual_average": ctx.get("annual_average"),
            # World-scale band label captured at FREEZE time (None for numeric/letter
            # schools, so old/numeric snapshots are visually unchanged). Per-term bands
            # already ride along inside term_rows from annual_report_context.
            "annual_band": ctx.get("annual_band"),
            "class_position": ctx.get("class_position"),
            "class_size": ctx.get("class_size"),
            "class_rank_display": ctx.get("class_rank_display"),
            "specialty_position": ctx.get("specialty_position"),
            "specialty_size": ctx.get("specialty_size"),
            "specialty_rank_display": ctx.get("specialty_rank_display"),
            "school_position": ctx.get("school_position"),
            "school_size": ctx.get("school_size"),
            "school_rank_display": ctx.get("school_rank_display"),
            "promotion_status": ctx.get("promotion_status"),
            "promotion_average": ctx.get("promotion_average"),
            "demotion_average": ctx.get("demotion_average"),
            "teacher_remark": ctx.get("teacher_remark"),
            "labels": ctx.get("labels"),
            "metadata": ctx.get("metadata"),
        }
        # Optional: format scores for region via TranscriptLocalizer
        try:
            from apps.reports.localization import get_transcript_localizer

            region_code = None
            if getattr(student, "school", None):
                region_code = getattr(student.school, "region_code", None) or getattr(
                    student.school, "region", None
                )
            loc = get_transcript_localizer(region_code=region_code)
            snapshot["region"] = loc.region.name if loc.region else "Default"
            snapshot["language"] = loc.language
        except _STUDENT360_SERVICE_ERRORS:
            snapshot["region"] = None
            snapshot["language"] = "en"
        return snapshot
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "build_transcript_snapshot failed",
            school_id=getattr(getattr(student, "school", None), "id", None),
            extra={
                "student_id": getattr(student, "id", None),
                "academic_year_id": getattr(academic_year, "id", None),
            },
        )
        return None


def create_immutable_transcript(
    student, academic_year, created_by=None, allow_refreeze=False
):
    """
    Freeze current transcript for this student and academic year into ImmutableTranscript.

    Write-once by DEFAULT: if a snapshot already exists for
    ``(student, academic_year)`` it is PRESERVED and returned unchanged — an
    "immutable" transcript must never be silently overwritten. The rollover /
    year-close archive relies on this so a re-run cannot clobber a graduating
    cohort's final, already-frozen transcript.

    Pass ``allow_refreeze=True`` for the deliberate, audited re-freeze that
    REPLACES the stored snapshot (e.g. the human-initiated freeze surface).
    Returns the ImmutableTranscript instance or None on failure.
    """
    try:
        from .models import ImmutableTranscript

        if not allow_refreeze:
            # Write-once: an existing frozen snapshot wins. Return it untouched
            # WITHOUT rebuilding, so the first freeze is preserved even if the
            # underlying report data has since changed or become unavailable.
            existing = ImmutableTranscript.objects.filter(
                student=student, academic_year=academic_year
            ).first()
            if existing is not None:
                return existing

        snapshot = build_transcript_snapshot(student, academic_year)
        if not snapshot:
            return None
        if allow_refreeze:
            # Deliberate, audited re-freeze — replace the stored snapshot.
            obj, _ = ImmutableTranscript.objects.update_or_create(
                student=student,
                academic_year=academic_year,
                defaults={"snapshot": snapshot, "created_by": created_by},
            )
        else:
            # First freeze — create the write-once row. get_or_create also guards
            # the check-then-create race against the unique_together constraint.
            obj, _ = ImmutableTranscript.objects.get_or_create(
                student=student,
                academic_year=academic_year,
                defaults={"snapshot": snapshot, "created_by": created_by},
            )
        return obj
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "create_immutable_transcript failed",
            school_id=getattr(getattr(student, "school", None), "id", None),
            extra={
                "student_id": getattr(student, "id", None),
                "academic_year_id": getattr(academic_year, "id", None),
            },
        )
        return None


def get_immutable_transcripts_for_student(student):
    """Return immutable transcripts for a student, newest academic year first (cross-year archive)."""
    try:
        from .models import ImmutableTranscript

        return list(
            ImmutableTranscript.objects.filter(student=student)
            .select_related("academic_year", "created_by")
            .order_by("-academic_year__start_date", "-created_at")
        )
    except _STUDENT360_SERVICE_ERRORS:
        log_exception_with_context(
            "get_immutable_transcripts_for_student failed",
            school_id=getattr(getattr(student, "school", None), "id", None),
            extra={"student_id": getattr(student, "id", None)},
        )
        return []
