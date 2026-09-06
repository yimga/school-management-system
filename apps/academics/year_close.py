"""
Academic year close — dry-run blockers and tenant-scoped rollover gates.
"""

from __future__ import annotations

from typing import Any


def academic_year_close_in_progress(school) -> bool:
    """True when tenant settings mark an in-flight academic year close."""
    settings = getattr(school, "settings", None) or {}
    if isinstance(settings, dict):
        return bool(settings.get("academic_year_close_in_progress"))
    return False


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
    from apps.academics.models import Classroom, Term
    from apps.academics.promotion_mappings import promotion_mapping_coverage
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

    # Terms are carried as OBJECTS, not ids, so a blocker can say WHICH term is
    # not ready. "1 term(s) not published" and "Grade approvals incomplete for
    # one or more terms" are both true and neither tells a head teacher where to
    # go; a rollover is only as automatic as its refusals are specific.
    terms = list(
        Term.objects.filter(  # tenant-isolation-allow: terms-scoped-via-validated-academic-year-fk
            academic_year=source_year
        ).order_by("position", "start_date")
    )
    unpublished_terms: list[int] = []
    approval_blockers: list[str] = []
    unpublished_labels: list[str] = []
    approval_labels: list[str] = []
    for term in terms:
        label = term.custom_label or term.name
        published = TermPublishStatus.objects.filter(
            academic_year_id=source_year.pk,
            term_id=term.pk,
            classroom__isnull=True,
            is_published=True,
        ).exists()
        if not published:
            unpublished_terms.append(term.pk)
            unpublished_labels.append(label)
        readiness = grade_approval_publish_readiness(source_year.pk, term.pk)
        if not readiness.get("ready_for_publish"):
            approval_blockers.append(str(term.pk))
            approval_labels.append(label)

    if unpublished_terms:
        blockers.append(
            {
                "code": "terms_unpublished",
                "message": (
                    f"{len(unpublished_terms)} term(s) not published for "
                    f"year-end: {', '.join(unpublished_labels)}."
                ),
            }
        )
    if approval_blockers:
        blockers.append(
            {
                "code": "grades_not_approved",
                "message": (
                    "Grade approvals incomplete for "
                    f"{len(approval_blockers)} term(s): "
                    f"{', '.join(approval_labels)}."
                ),
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

    # Can every populated classroom actually move its students forward? An
    # advancing student whose classroom has no ClassroomPromotionMapping is
    # SKIPPED by the promotion run -- one warning line among many -- so the
    # question has to be asked before the source year is locked behind them.
    #
    # Only asked once the target year has been structured. Before the clone the
    # target has no classrooms to map ONTO, so the answer would be "none of
    # them" for every school, every time, which is a blocker nobody can clear.
    target_structured = Classroom.objects.filter(  # tenant-isolation-allow: bounded-by-the-school-owned-academic-year-fk
        academic_year=target_year
    ).exists()
    coverage = (
        promotion_mapping_coverage(source_year, target_year, school=school)
        if target_structured
        else {"total": 0, "mapped": 0, "unmapped": 0, "unmapped_classrooms": []}
    )
    if coverage["unmapped"]:
        named = ", ".join(c["name"] for c in coverage["unmapped_classrooms"][:5])
        if coverage["unmapped"] > 5:
            named += ", ..."
        blockers.append(
            {
                "code": "promotion_mapping_missing",
                "message": (
                    f"{coverage['unmapped']} of {coverage['total']} classroom(s) "
                    f"have no promotion mapping into the target year ({named}). "
                    "Advancing students in them would be skipped."
                ),
            }
        )

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
            "terms_missing_approval": len(approval_blockers),
            "returns_blocked_students": returns_blocked,
            "finance_blocked_students": finance_blocked,
            "populated_classrooms": coverage["total"],
            "mapped_classrooms": coverage["mapped"],
            "unmapped_classrooms": coverage["unmapped"],
        },
        "promotion_mapping_coverage": coverage,
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


#: Domains that hard-closed years refuse by default (Salesforce Soft/Hard Close parity).
PERIOD_WRITE_DOMAINS = frozenset(
    {
        "grades",
        "enrollment",
        "rollover_source",
        "attendance",
        "timetable",
        "finance_charges",
    }
)

#: Soft Close only constrains these domains for non-elevated actors (P1 = grades).
SOFT_CLOSE_DOMAINS = frozenset({"grades"})

_MIN_UNLOCK_REASON_CHARS = 12
_MIN_SOFT_REASON_CHARS = 8


def _actor_may_write_soft_closed_grades(actor, school) -> bool:
    """Registrars / grades.manage / tenant admin may correct during Soft Close."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False) or getattr(actor, "is_staff", False):
        return True
    try:
        from apps.accounts.decorators import user_has_permission

        return bool(
            user_has_permission(
                actor,
                school,
                codes=("grades.manage",),
                allow_admin=True,
            )
        )
    except (ImportError, TypeError, AttributeError):
        return False


def _refresh_close_flags(academic_year) -> tuple[bool, bool]:
    """Return (is_locked, is_soft_closed).

    Trusts in-memory True flags (callers that set attributes without save).
    Re-reads the DB only to catch stale False after ``lock_source_year`` /
    soft-close services updated another copy of the same PK.
    """
    locked = bool(getattr(academic_year, "is_locked", False))
    soft = bool(getattr(academic_year, "is_soft_closed", False))
    pk = getattr(academic_year, "pk", None)
    if not pk or (locked and soft):
        return locked, soft
    from apps.academics.models import AcademicYear

    row = (
        AcademicYear.objects.filter(pk=pk)
        .values_list("is_locked", "is_soft_closed")
        .first()
    )
    if row is None:
        return locked, soft
    return locked or bool(row[0]), soft or bool(row[1])


def assert_period_writable(
    academic_year,
    *,
    domain: str = "grades",
    actor=None,
    school=None,
) -> None:
    """Central Soft/Hard Close write guard (entrypoints + APIs should call this).

    - Hard Close (``is_locked``): all listed domains blocked for everyone.
    - Soft Close (``is_soft_closed``): ``grades`` blocked for teachers; elevated
      ``grades.manage`` / admin / staff / superuser may still write.
    - Lock does **not** control the tenant default year — that is ``is_active``.

    Re-reads close flags from the DB when a PK is present so callers with a
    stale in-memory instance cannot bypass.
    """
    from django.core.exceptions import ValidationError

    if academic_year is None:
        return
    if domain not in PERIOD_WRITE_DOMAINS:
        domain = "grades"
    locked, soft = _refresh_close_flags(academic_year)
    name = getattr(academic_year, "name", None) or academic_year
    if locked:
        raise ValidationError(
            f"Academic year '{name}' is hard-closed ({domain}); "
            "use audited unlock (break-glass) before writing."
        )
    if soft and domain in SOFT_CLOSE_DOMAINS:
        sch = school or getattr(academic_year, "school", None)
        if not _actor_may_write_soft_closed_grades(actor, sch):
            raise ValidationError(
                f"Academic year '{name}' is soft-closed ({domain}); "
                "teachers cannot edit — contact a registrar with grades.manage."
            )


def soft_close_academic_year(
    school,
    academic_year,
    *,
    actor=None,
    reason: str = "",
) -> dict[str, Any]:
    """Soft-close a year (teachers blocked on grades; admins may still correct)."""
    from django.db import transaction
    from django.utils import timezone

    from apps.academics.models import AcademicYear

    if getattr(academic_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    reason_text = (reason or "soft close — grading review window").strip()[:255]
    if len(reason_text) < _MIN_SOFT_REASON_CHARS:
        raise ValueError(
            f"Soft-close reason must be at least {_MIN_SOFT_REASON_CHARS} characters."
        )
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=academic_year.pk)
        if year.is_locked:
            raise ValueError(
                "Year is hard-closed; unlock before changing soft-close state."
            )
        already = bool(year.is_soft_closed)
        if not already:
            year.is_soft_closed = True
            year.soft_closed_at = timezone.now()
            year.soft_closed_by = actor if getattr(actor, "pk", None) else None
            year.soft_close_reason = reason_text
            year.save(
                update_fields=[
                    "is_soft_closed",
                    "soft_closed_at",
                    "soft_closed_by",
                    "soft_close_reason",
                    "updated_at",
                ]
            )
    return {
        "ok": True,
        "already_soft_closed": already,
        "year_id": str(academic_year.pk),
        "actor_id": getattr(actor, "pk", None),
    }


def reopen_soft_closed_year(
    school,
    academic_year,
    *,
    actor=None,
    reason: str = "",
) -> dict[str, Any]:
    """Reopen Soft Close (audited). Does not clear Hard Close."""
    from django.db import transaction
    from django.utils import timezone

    from apps.academics.models import AcademicYear

    if getattr(academic_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    reason_text = (reason or "").strip()
    if len(reason_text) < _MIN_SOFT_REASON_CHARS:
        raise ValueError(
            f"Reopen reason must be at least {_MIN_SOFT_REASON_CHARS} characters."
        )
    reason_text = reason_text[:255]
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=academic_year.pk)
        if year.is_locked:
            raise ValueError(
                "Year is hard-closed; use unlock_academic_year (break-glass) first."
            )
        if not year.is_soft_closed:
            return {
                "ok": True,
                "already_open": True,
                "year_id": str(year.pk),
            }
        year.is_soft_closed = False
        year.soft_reopened_at = timezone.now()
        year.soft_reopened_by = actor if getattr(actor, "pk", None) else None
        year.soft_reopen_reason = reason_text
        year.save(
            update_fields=[
                "is_soft_closed",
                "soft_reopened_at",
                "soft_reopened_by",
                "soft_reopen_reason",
                "updated_at",
            ]
        )
    return {
        "ok": True,
        "already_open": False,
        "year_id": str(academic_year.pk),
        "actor_id": getattr(actor, "pk", None),
    }


def activate_academic_year(school, academic_year, *, actor=None) -> dict[str, Any]:
    """Pin the tenant default year (``is_active``) — exclusive per school.

    PowerSchool / FACTS / Infinite Campus parity: the operating year is an
    explicit pin, never implied by lock state.
    """
    from django.db import transaction

    from apps.academics.models import AcademicYear

    if getattr(academic_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=academic_year.pk)
        AcademicYear.objects.filter(school=school, is_active=True).exclude(
            pk=year.pk
        ).update(is_active=False)
        if not year.is_active:
            year.is_active = True
            year.save(update_fields=["is_active", "updated_at"])
            already = False
        else:
            already = True
    return {
        "ok": True,
        "already_active": already,
        "year_id": str(year.pk),
        "actor_id": getattr(actor, "pk", None),
    }


def lock_source_year(
    school,
    source_year,
    *,
    actor=None,
    reason: str = "",
    activate_target=None,
) -> dict[str, Any]:
    """Hard-close source academic year (tenant-scoped) with provenance.

    Optionally activate ``activate_target`` as the new tenant default — the
    correct post-rollover contract (lock source ≠ make source default).
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.academics.models import AcademicYear

    if getattr(source_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    if activate_target is not None and getattr(
        activate_target, "school_id", None
    ) != getattr(school, "pk", None):
        raise ValueError("Target academic year does not belong to this school.")

    reason_text = (reason or "year-end hard close").strip()[:255]
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=source_year.pk)
        already = bool(year.is_locked)
        if not already:
            year.is_locked = True
            year.locked_at = timezone.now()
            year.locked_by = actor if getattr(actor, "pk", None) else None
            year.lock_reason = reason_text
            year.save(
                update_fields=[
                    "is_locked",
                    "locked_at",
                    "locked_by",
                    "lock_reason",
                    "updated_at",
                ]
            )
        activate_result = None
        if activate_target is not None:
            activate_result = activate_academic_year(
                school, activate_target, actor=actor
            )
    return {
        "ok": True,
        "already_locked": already,
        "year_id": str(source_year.pk),
        "activate": activate_result,
    }


def unlock_academic_year(
    school,
    academic_year,
    *,
    actor=None,
    reason: str = "",
) -> dict[str, Any]:
    """Break-glass reopen of a hard-closed year (tenant admin / superuser path).

    Requires a non-trivial reason. Does **not** change ``is_active`` — the
    operating default stays on whatever year is currently pinned.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.academics.models import AcademicYear

    if getattr(academic_year, "school_id", None) != getattr(school, "pk", None):
        raise ValueError("Academic year does not belong to this school.")
    reason_text = (reason or "").strip()
    if len(reason_text) < _MIN_UNLOCK_REASON_CHARS:
        raise ValueError(
            f"Unlock reason must be at least {_MIN_UNLOCK_REASON_CHARS} characters."
        )
    reason_text = reason_text[:255]
    with transaction.atomic():
        year = AcademicYear.objects.select_for_update().get(pk=academic_year.pk)
        if not year.is_locked:
            return {
                "ok": True,
                "already_unlocked": True,
                "year_id": str(year.pk),
            }
        year.is_locked = False
        year.unlocked_at = timezone.now()
        year.unlocked_by = actor if getattr(actor, "pk", None) else None
        year.unlock_reason = reason_text
        year.save(
            update_fields=[
                "is_locked",
                "unlocked_at",
                "unlocked_by",
                "unlock_reason",
                "updated_at",
            ]
        )
    return {
        "ok": True,
        "already_unlocked": False,
        "year_id": str(academic_year.pk),
        "actor_id": getattr(actor, "pk", None),
    }


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
    activate_target_on_lock: bool = True,
    actor=None,
    lock_reason: str = "",
) -> dict[str, Any]:
    """
    Top-level year-close orchestrator — dry-run by default (no writes).

    When ``lock_on_success`` and ``activate_target_on_lock``, hard-closes the
    source year and pins the target as the tenant default (competitor EOY
    parity). Lock alone never makes the source year the default.
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
        steps["lock"] = lock_source_year(
            school,
            source_year,
            actor=actor,
            reason=lock_reason or "execute_year_close lock_on_success",
            activate_target=target_year if activate_target_on_lock else None,
        )
    return {"ok": True, "dry_run": False, "scorecard": scorecard, "steps": steps}
