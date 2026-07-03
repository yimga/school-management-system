"""School merge / split batch engine (Wave D, design §10).

Composes the proven rails and adds none of its own: every student moves
through the UNMODIFIED Wave B ``run_transfer_case`` (per-case lock,
offline-pending guard, compensation, reconcile), fanned out and rolled up by
the batch. Advancement is chunked and idempotent — a duplicate or late tick
re-runs nothing already applied — and per-case failures are isolated behind a
3-attempt ledger so one stuck student never strands a school merger.

Wind-down (merge only) is a HANDOFF to the existing offboarding rails
(portability export + lifecycle deactivate). The batch never purges — that
stays in the offboarding console behind its own dual approval + legal hold.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Cases per advance tick — small on purpose: each case is a full envelope
#: export + migration-cloud apply.
DEFAULT_CHUNK = 5
#: A case that refuses to run this many times (offline blockers, transient
#: guard failures) is counted as an issue and no longer retried automatically.
MAX_CASE_ATTEMPTS = 3

#: Statuses meaning "this student is already moving/moved to the target" —
#: a re-started batch skips them (idempotency).
_LIVE_OR_DONE_CASE_STATUSES = (
    "draft",
    "consent_pending",
    "approved",
    "exporting",
    "envelope_sealed",
    "applying",
    "applied",
    "reconciled",
)
#: Case statuses still owed an outcome — the batch cannot complete over them.
_OPEN_CASE_STATUSES = (
    "draft",
    "consent_pending",
    "exporting",
    "envelope_sealed",
    "applying",
    "compensating",
)


class BatchBlockedError(RuntimeError):
    """A guard refused the batch action — the batch FSM was NOT advanced."""


def _batch_domains() -> list[str]:
    # Same rule as the single-case console: grades stay out until the grades
    # lander resolves term/subject FKs at the target.
    from apps.interop.student_transfer_export import TRANSFER_DEFAULT_DOMAINS

    return [d for d in TRANSFER_DEFAULT_DOMAINS if d != "grades"]


def eligible_student_qs(batch):
    """Active source students in the batch's cohort (design DR7)."""
    from apps.people.models import StudentProfile

    qs = StudentProfile.objects.filter(
        school=batch.source_school, is_active=True, merged_into__isnull=True
    ).exclude(status=StudentProfile.Status.TRANSFERRED)
    cohort = batch.cohort or {}
    classroom_ids = [c for c in (cohort.get("classroom_ids") or []) if c]
    student_pks = [s for s in (cohort.get("student_pks") or []) if s]
    if classroom_ids or student_pks:
        selector = Q()
        if classroom_ids:
            selector |= Q(classroom_id__in=classroom_ids)
        if student_pks:
            selector |= Q(pk__in=student_pks)
        qs = qs.filter(selector)
    return qs


def _already_covered_pks(batch) -> set[str]:
    from apps.people.models_transfer import TransferCase

    rows = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-source-target-scoped
        source_school=batch.source_school,
        target_school=batch.target_school,
        status__in=_LIVE_OR_DONE_CASE_STATUSES,
    ).values_list("source_profile_pk", flat=True)
    return {str(pk) for pk in rows}


def preview_batch(batch) -> dict[str, Any]:
    """Count the fan-out; advance to PREVIEWED."""
    from apps.people.models_school_batch import SchoolTransferBatch

    if batch.status not in (
        SchoolTransferBatch.Status.DRAFT,
        SchoolTransferBatch.Status.PREVIEWED,
    ):
        raise BatchBlockedError(f"cannot preview from {batch.status!r}")

    covered = _already_covered_pks(batch)
    eligible = list(
        eligible_student_qs(batch).values_list("pk", "first_name", "last_name")
    )
    to_move = [row for row in eligible if str(row[0]) not in covered]
    batch.preview = {
        "eligible": len(eligible),
        "already_in_flight_or_moved": len(eligible) - len(to_move),
        "to_move": len(to_move),
        "sample": [
            {"pk": str(pk), "name": f"{first} {last}".strip()}
            for pk, first, last in to_move[:10]
        ],
        "domains": _batch_domains(),
        "generated_at": timezone.now().isoformat(),
    }
    batch.save(update_fields=["preview", "updated_at"])
    batch.advance(
        SchoolTransferBatch.Status.PREVIEWED,
        note=f"{len(to_move)} student(s) to move ({len(eligible)} eligible)",
    )
    return batch.preview


def record_batch_approval(batch, actor, confirm_slug: str) -> dict[str, Any]:
    """Purge-grammar dual approval: two DISTINCT staff operators, each retyping
    the source school's slug. First call journals the primary approver; the
    second (different) operator completes the approval."""
    from apps.people.models_school_batch import SchoolTransferBatch

    if batch.status != SchoolTransferBatch.Status.PREVIEWED:
        raise BatchBlockedError(f"cannot approve from {batch.status!r} — preview first")
    if (confirm_slug or "").strip() != batch.source_school.slug:
        raise BatchBlockedError(
            "confirmation does not match the source school slug — type it exactly"
        )
    if not getattr(actor, "pk", None) or not getattr(actor, "is_staff", False):
        raise BatchBlockedError("approval requires an authenticated staff operator")
    if (
        batch.consent_mode == SchoolTransferBatch.ConsentMode.INSTITUTIONAL
        and not (batch.consent_basis or "").strip()
    ):
        raise BatchBlockedError(
            "institutional mode requires a recorded consent_basis "
            "(board resolution / ministry order) before approval"
        )

    if batch.approved_by_primary_id is None:
        batch.approved_by_primary = actor
        batch.save(update_fields=["approved_by_primary", "updated_at"])
        batch.advance(
            SchoolTransferBatch.Status.PREVIEWED,
            note=f"primary approval by {getattr(actor, 'username', '')}"[:200],
        )
        return {"approved": False, "awaiting": "secondary approver"}
    if batch.approved_by_primary_id == actor.pk:
        raise BatchBlockedError(
            "dual approval requires a second, DISTINCT operator"
        )
    batch.approved_by_secondary = actor
    batch.save(update_fields=["approved_by_secondary", "updated_at"])
    batch.advance(
        SchoolTransferBatch.Status.APPROVED,
        note=f"secondary approval by {getattr(actor, 'username', '')}"[:200],
    )
    _audit(batch, actor, "batch dual-approved")
    return {"approved": True}


def start_batch(batch, actor=None) -> dict[str, Any]:
    """Fan out one TransferCase per eligible student; batch → RUNNING."""
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    if batch.status != SchoolTransferBatch.Status.APPROVED:
        raise BatchBlockedError(f"cannot start from {batch.status!r}")

    covered = _already_covered_pks(batch)
    domains = _batch_domains()
    institutional = (
        batch.consent_mode == SchoolTransferBatch.ConsentMode.INSTITUTIONAL
    )
    created = 0
    skipped = 0
    for profile in eligible_student_qs(batch).iterator():
        if str(profile.pk) in covered:
            skipped += 1
            continue
        case = TransferCase.objects.create(
            batch=batch,
            source_school=batch.source_school,
            target_school=batch.target_school,
            source_profile_pk=str(profile.pk),
            domains=domains,
            consent_reference=f"batch:{batch.pk}",
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        if institutional:
            # The consent artifact for the whole batch is the dual-approved
            # institutional basis; each case journals it through the normal
            # FSM stations so the audit trail reads the same as Wave B.
            case.advance(
                TransferCase.Status.CONSENT_PENDING,
                note=f"institutional consent basis on batch {batch.pk}",
            )
            case.advance(
                TransferCase.Status.APPROVED,
                note=(
                    f"institutional authority — batch dual-approved "
                    f"({(batch.consent_basis or '')[:120]})"
                ),
            )
        created += 1

    batch.advance(
        SchoolTransferBatch.Status.RUNNING,
        note=(
            f"{created} case(s) opened, {skipped} already in flight/moved"
            + ("" if institutional else " — awaiting per-guardian consent")
        ),
    )
    _audit(batch, actor, f"batch started ({created} cases)")
    return {"cases_created": created, "skipped": skipped}


def advance_batch(batch, *, actor=None, max_cases: int = DEFAULT_CHUNK) -> dict[str, Any]:
    """Run up to ``max_cases`` APPROVED cases; roll up and maybe complete."""
    from django.core.cache import cache

    lock_key = f"rmc-school-batch-run-{batch.pk}"
    if not cache.add(lock_key, "1", timeout=600):  # magic-number-allow: single-flight-lock-ttl-seconds
        raise BatchBlockedError("an advance is already in flight for this batch")
    try:
        return _advance_batch_locked(batch, actor=actor, max_cases=max_cases)
    finally:
        cache.delete(lock_key)


def _advance_batch_locked(batch, *, actor, max_cases: int) -> dict[str, Any]:
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase
    from apps.people.transfer_service import TransferBlockedError, run_transfer_case

    batch.refresh_from_db()
    if batch.status != SchoolTransferBatch.Status.RUNNING:
        raise BatchBlockedError(f"batch is not running (status={batch.status!r})")

    ledger = dict(batch.ledger or {})

    def _attempts(case_pk) -> int:
        return int((ledger.get(str(case_pk)) or {}).get("attempts") or 0)

    runnable = [
        case
        for case in TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
            batch=batch, status=TransferCase.Status.APPROVED
        ).order_by("created_at")
        if _attempts(case.pk) < MAX_CASE_ATTEMPTS
    ][: max(1, int(max_cases))]

    ran = 0
    blocked = 0
    failed = 0
    for case in runnable:
        try:
            run_transfer_case(case, actor=actor)
            ran += 1
            ledger.pop(str(case.pk), None)
        except TransferBlockedError as exc:
            blocked += 1
            entry = ledger.get(str(case.pk)) or {}
            ledger[str(case.pk)] = {
                "attempts": int(entry.get("attempts") or 0) + 1,
                "last_error": str(exc)[:300],
                "at": timezone.now().isoformat(),
            }
        except Exception as exc:  # noqa: BLE001 — the case's own FSM landed FAILED/compensated; the batch records and continues
            failed += 1
            entry = ledger.get(str(case.pk)) or {}
            ledger[str(case.pk)] = {
                "attempts": int(entry.get("attempts") or 0) + 1,
                "last_error": f"{type(exc).__name__}: {exc}"[:300],
                "at": timezone.now().isoformat(),
            }
            logger.warning(
                "school_batch.case_failed batch=%s case=%s", batch.pk, case.pk
            )

    batch.ledger = ledger
    batch.save(update_fields=["ledger", "updated_at"])

    summary = _maybe_complete(batch, ledger)
    summary.update({"ran": ran, "blocked": blocked, "failed": failed})
    return summary


def _maybe_complete(batch, ledger) -> dict[str, Any]:
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    cases = TransferCase.objects.filter(batch=batch)  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
    open_count = cases.filter(status__in=_OPEN_CASE_STATUSES).count()
    approved = list(cases.filter(status=TransferCase.Status.APPROVED))
    exhausted = [
        c
        for c in approved
        if int((ledger.get(str(c.pk)) or {}).get("attempts") or 0)
        >= MAX_CASE_ATTEMPTS
    ]
    runnable_left = len(approved) - len(exhausted)
    issues = (
        cases.filter(
            status__in=(TransferCase.Status.FAILED, TransferCase.Status.CANCELLED)
        ).count()
        + len(exhausted)
    )
    succeeded = cases.filter(
        status__in=(TransferCase.Status.APPLIED, TransferCase.Status.RECONCILED)
    ).count()

    if open_count == 0 and runnable_left == 0:
        target = (
            SchoolTransferBatch.Status.COMPLETED
            if issues == 0
            else SchoolTransferBatch.Status.COMPLETED_WITH_ISSUES
        )
        batch.completed_at = timezone.now()
        batch.save(update_fields=["completed_at", "updated_at"])
        batch.advance(
            target,
            note=f"{succeeded} succeeded, {issues} issue(s)",
        )
    return {
        "status": batch.status,
        "open": open_count,
        "runnable_left": runnable_left,
        "succeeded": succeeded,
        "issues": issues,
    }


def cancel_batch(batch, *, actor=None, note: str = "") -> None:
    """Stop the batch: no further scheduling. In-flight cases finish their own
    FSM; already-opened APPROVED cases stay for the single-case console."""
    from apps.people.models_school_batch import SchoolTransferBatch

    batch.advance(
        SchoolTransferBatch.Status.CANCELLED,
        note=(note or f"cancelled by {getattr(actor, 'username', '')}")[:200],
    )
    _audit(batch, actor, "batch cancelled")


def wind_down_source(batch, *, actor, confirm_slug: str) -> dict[str, Any]:
    """Merge handoff (DR5): portability export + lifecycle deactivate of the
    source. Refuses while any case is unfinished. NEVER purges."""
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    if batch.kind != SchoolTransferBatch.Kind.MERGE:
        raise BatchBlockedError("wind-down applies to merge batches only")
    if batch.status not in (
        SchoolTransferBatch.Status.COMPLETED,
        SchoolTransferBatch.Status.COMPLETED_WITH_ISSUES,
    ):
        raise BatchBlockedError(
            f"batch must be completed before wind-down (status={batch.status!r})"
        )
    if (confirm_slug or "").strip() != batch.source_school.slug:
        raise BatchBlockedError(
            "confirmation does not match the source school slug — type it exactly"
        )
    if (batch.wind_down or {}).get("deactivated"):
        raise BatchBlockedError("source school is already wound down for this batch")
    unfinished = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
        batch=batch,
        status__in=_OPEN_CASE_STATUSES + ("approved",),
    ).count()
    if unfinished:
        raise BatchBlockedError(
            f"{unfinished} case(s) still unfinished — resolve or abort them first"
        )

    from apps.schools.tenant_offboarding import (
        run_wind_down_deactivate,
        run_wind_down_export,
    )

    export = run_wind_down_export(batch.source_school, full=True, actor=actor)
    run_wind_down_deactivate(batch.source_school, actor=actor)
    batch.wind_down = {
        "export_zip": export.export_zip_path,
        "student_export_count": export.student_export_count,
        "deactivated": True,
        "at": timezone.now().isoformat(),
        "by": getattr(actor, "pk", None),
    }
    batch.save(update_fields=["wind_down", "updated_at"])
    batch.history = [
        *(batch.history or []),
        {
            "note": "source wound down (export + deactivate); purge stays in the offboarding console",
            "at": timezone.now().isoformat(),
        },
    ]
    batch.save(update_fields=["history", "updated_at"])
    _audit(batch, actor, "source wound down (export + deactivate)")
    return dict(batch.wind_down)


def advance_running_batches(*, max_batches: int = 5, max_cases: int = DEFAULT_CHUNK) -> dict[str, Any]:
    """Periodic-job entry: advance each RUNNING batch one chunk."""
    from apps.people.models_school_batch import SchoolTransferBatch

    outcomes = []
    batches = SchoolTransferBatch.objects.filter(  # tenant-isolation-allow: operator-plane-batch-advancer-cross-tenant-by-design
        status=SchoolTransferBatch.Status.RUNNING
    ).order_by("created_at")[: max(1, int(max_batches))]
    for batch in batches:
        try:
            outcomes.append(
                {"batch": str(batch.pk), **advance_batch(batch, max_cases=max_cases)}
            )
        except BatchBlockedError as exc:
            outcomes.append({"batch": str(batch.pk), "skipped": str(exc)[:200]})
    return {"advanced": len(outcomes), "outcomes": outcomes}


def _audit(batch, actor, note: str) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            user=actor if getattr(actor, "pk", None) else None,
            model_name="SchoolTransferBatch",
            object_id=str(batch.pk)[:200],
            object_repr=(
                f"{batch.kind} batch {batch.source_school_id} → "
                f"{batch.target_school_id} ({note})"
            )[:200],
            app_label="people",
            new_values={"status": batch.status},
        )
    except Exception:  # noqa: BLE001 — audit never blocks a batch
        logger.warning("school_batch.audit_failed batch=%s", batch.pk)


__all__ = [
    "DEFAULT_CHUNK",
    "MAX_CASE_ATTEMPTS",
    "BatchBlockedError",
    "advance_batch",
    "advance_running_batches",
    "cancel_batch",
    "eligible_student_qs",
    "preview_batch",
    "record_batch_approval",
    "start_batch",
    "wind_down_source",
]
