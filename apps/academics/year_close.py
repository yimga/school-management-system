"""
Academic year close — dry-run blockers and tenant-scoped rollover gates.
"""

from __future__ import annotations

from typing import Any


def evaluate_year_close_blockers(
    school,
    source_year,
    target_year,
    *,
    require_financial_clearance: bool = False,
) -> dict[str, Any]:
    """
    Read-only blocker scorecard for year-end rollover.
    Safe to call with dry_run=True semantics (no writes).
    """
    from apps.academics.models import Term
    from apps.people.models import StudentProfile
    from apps.reports.models import TermPublishStatus
    from apps.reports.services import (
        grade_approval_publish_readiness,
        student_has_financial_clearance,
        student_has_outstanding_returns,
    )

    blockers: list[dict[str, str]] = []
    if getattr(source_year, "is_locked", False):
        blockers.append(
            {
                "code": "source_year_locked",
                "message": "Source academic year is already locked.",
            }
        )
    if source_year.pk == target_year.pk:
        blockers.append(
            {"code": "same_year", "message": "Source and target year must differ."}
        )
    if getattr(source_year, "school_id", None) != getattr(school, "pk", None):
        blockers.append(
            {
                "code": "tenant_mismatch",
                "message": "Academic year does not belong to this school.",
            }
        )

    terms = list(
        Term.objects.filter(academic_year=source_year).values_list("id", flat=True)
    )
    unpublished_terms: list[int] = []
    approval_blockers: list[str] = []
    for term_id in terms:
        published = TermPublishStatus.objects.filter(
            academic_year_id=source_year.pk,
            term_id=term_id,
            classroom__isnull=True,
            is_published=True,
        ).exists()
        if not published:
            unpublished_terms.append(term_id)
        readiness = grade_approval_publish_readiness(source_year.pk, term_id)
        if not readiness.get("ready_for_publish"):
            approval_blockers.append(str(term_id))

    if unpublished_terms:
        blockers.append(
            {
                "code": "terms_unpublished",
                "message": f"{len(unpublished_terms)} term(s) not published for year-end.",
            }
        )
    if approval_blockers:
        blockers.append(
            {
                "code": "grades_not_approved",
                "message": "Grade approvals incomplete for one or more terms.",
            }
        )

    students = StudentProfile.objects.filter(school=school, is_active=True)
    returns_blocked = 0
    finance_blocked = 0
    for student in students.iterator(chunk_size=200):
        if student_has_outstanding_returns(student, source_year):
            returns_blocked += 1
        if require_financial_clearance and not student_has_financial_clearance(
            student, source_year
        ):
            finance_blocked += 1

    if returns_blocked:
        blockers.append(
            {
                "code": "outstanding_returns",
                "message": f"{returns_blocked} student(s) have outstanding resource returns.",
            }
        )
    if finance_blocked:
        blockers.append(
            {
                "code": "financial_clearance",
                "message": f"{finance_blocked} student(s) lack financial clearance.",
            }
        )

    return {
        "ok": not blockers,
        "dry_run": True,
        "source_year_id": str(source_year.pk),
        "target_year_id": str(target_year.pk),
        "blockers": blockers,
        "counts": {
            "unpublished_terms": len(unpublished_terms),
            "returns_blocked_students": returns_blocked,
            "finance_blocked_students": finance_blocked,
        },
    }


def assert_rollover_allowed(
    school,
    source_year,
    target_year,
    *,
    require_financial_clearance: bool = False,
) -> None:
    result = evaluate_year_close_blockers(
        school,
        source_year,
        target_year,
        require_financial_clearance=require_financial_clearance,
    )
    if not result["ok"]:
        messages = "; ".join(b["message"] for b in result["blockers"])
        raise ValueError(messages or "Year close blockers present.")


def run_year_close_dry_run(
    school,
    source_year,
    target_year,
    *,
    require_financial_clearance: bool = False,
) -> dict[str, Any]:
    """Alias for evaluate_year_close_blockers — explicit dry-run entrypoint."""
    return evaluate_year_close_blockers(
        school,
        source_year,
        target_year,
        require_financial_clearance=require_financial_clearance,
    )


def lock_source_year(school, source_year) -> dict[str, Any]:
    """Lock source academic year after close (tenant-scoped)."""
    from django.db import transaction

    from apps.academics.models import AcademicYear

    if getattr(source_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=source_year.pk)
        if year.is_locked:
            return {"ok": True, "already_locked": True, "year_id": str(year.pk)}
        year.is_locked = True
        year.save(update_fields=["is_locked"])
    return {"ok": True, "already_locked": False, "year_id": str(source_year.pk)}


def batch_freeze_transcripts(school, source_year) -> dict[str, Any]:
    """Create immutable transcripts for active students (best-effort per row)."""
    from apps.people.models import StudentProfile
    from apps.student360.services import create_immutable_transcript

    created = 0
    errors = 0
    for student in StudentProfile.objects.filter(school=school, is_active=True):
        try:
            create_immutable_transcript(student, source_year)
            created += 1
        except (TypeError, ValueError, RuntimeError):
            errors += 1
    return {"ok": errors == 0, "created": created, "errors": errors}


def execute_year_close(
    school,
    source_year,
    target_year,
    *,
    dry_run: bool = True,
    require_financial_clearance: bool = False,
    lock_on_success: bool = False,
    freeze_transcripts: bool = False,
) -> dict[str, Any]:
    """
    Top-level year-close orchestrator — dry-run by default (no writes).
    """
    scorecard = evaluate_year_close_blockers(
        school,
        source_year,
        target_year,
        require_financial_clearance=require_financial_clearance,
    )
    if not scorecard["ok"]:
        return {"ok": False, "dry_run": dry_run, "scorecard": scorecard}
    if dry_run:
        return {"ok": True, "dry_run": True, "scorecard": scorecard}
    steps: dict[str, Any] = {}
    if freeze_transcripts:
        steps["transcripts"] = batch_freeze_transcripts(school, source_year)
    if lock_on_success:
        steps["lock"] = lock_source_year(school, source_year)
    return {"ok": True, "dry_run": False, "scorecard": scorecard, "steps": steps}
