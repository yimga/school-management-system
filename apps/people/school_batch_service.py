"""School merge / split batch engine (Wave D, design §10; D.1 audit closeout).

Composes the proven rails and adds none of its own: every student moves
through the UNMODIFIED Wave B ``run_transfer_case`` (per-case lock,
offline-pending guard, compensation, reconcile), fanned out and rolled up by
the batch. Advancement is chunked and idempotent — a duplicate or late tick
re-runs nothing already applied — and per-case failures are isolated behind a
3-attempt ledger so one stuck student never strands a school merger.

Wind-down (merge only) is a HANDOFF to the existing offboarding rails
(portability export + lifecycle deactivate). The batch never purges — that
stays in the offboarding console behind its own dual approval + legal hold.

D.1 concurrency contract: every status-mutating entry point either holds the
per-batch run lock (advance, cancel) or its own single-flight lock (start,
wind-down), and re-reads the DB row before advancing — the FSM's ``advance()``
trusts the in-memory instance, so a stale instance must never blind-write.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Cases per advance tick — small on purpose: each case is a full envelope
#: export + migration-cloud apply.
DEFAULT_CHUNK = 5
#: A case that refuses to run this many times (offline blockers, transient
#: guard failures) is counted as an issue and no longer retried automatically.
MAX_CASE_ATTEMPTS = 3
#: A case stranded in COMPENSATING longer than this was interrupted mid-
#: compensation (crash/deploy between the two advances) — the advancer reaps
#: it to FAILED so the batch can complete instead of hanging forever.
REAP_COMPENSATING_AFTER_SECONDS = 1800  # magic-number-allow: stale-compensation-reap-threshold-seconds

#: Statuses meaning "this student is already moving/moved out of the source" —
#: a re-started batch skips them (idempotency). D.1: deliberately NOT scoped
#: to one target — a student mid-transfer to ANY school must not be fanned
#: into a second concurrent move.
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


def _batch_domains(batch=None) -> list[str]:
    # Full default set (2026-07-09): the grades lander now resolves the
    # term/subject/assignment/teacher FK graph at the target, and every
    # evaluation ALSO rides the archival `transcripts` domain (vault items
    # need no target structure) — live rows where the graph resolves,
    # provenance-stamped vault records always.
    from apps.interop.student_transfer_export import TRANSFER_DEFAULT_DOMAINS

    domains = list(TRANSFER_DEFAULT_DOMAINS)
    # SPLIT-only academic scaffold (2026-07-09): a split lands its cohort into a
    # fresh/greenfield target that has none of the source's calendar, classes,
    # subjects or assignments, so enrollment + grades would quarantine 100% and
    # the split school would arrive with an empty gradebook. Prepend the
    # `structure` domain (StructureLander, wave 0) to PROVISION that scaffold
    # before students/enrollment/grades. A MERGE targets an existing school and
    # maps to its OWN structure — it never fabricates the source's.
    from apps.people.models_school_batch import SchoolTransferBatch

    if batch is not None and getattr(batch, "kind", None) == SchoolTransferBatch.Kind.SPLIT:
        domains = ["structure", *domains]
    return domains


def eligible_student_qs(batch):
    """Active, enrollable source students in the batch's cohort (design DR7).

    ALUMNI stay ``is_active=True`` as historical records — they are NOT
    enrollable and must never be fanned out as live transfers (they would
    land at the target as active students). Their records stay with the
    source tenant and ride the wind-down portability export. PROBATION
    students ARE still enrolled and move with the school — deliberate.
    """
    from apps.people.models import StudentProfile

    qs = StudentProfile.objects.filter(
        school=batch.source_school, is_active=True, merged_into__isnull=True
    ).exclude(
        status__in=[
            StudentProfile.Status.TRANSFERRED,
            StudentProfile.Status.ALUMNI,
        ]
    )
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
    """Students with a live or successful case out of the source — to ANY
    target (D.1: a student mid-move to school C must not also be fanned to
    school B; the transfer engine additionally refuses retired sources)."""
    from apps.people.models_transfer import TransferCase

    rows = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-source-school-scoped
        source_school=batch.source_school,
        status__in=_LIVE_OR_DONE_CASE_STATUSES,
    ).values_list("source_profile_pk", flat=True)
    return {str(pk) for pk in rows}


def _population_fingerprint(pks) -> str:
    canon = ",".join(sorted(str(pk) for pk in pks))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def preview_batch(batch) -> dict[str, Any]:
    """Count the fan-out; advance to PREVIEWED.

    Re-previewing RESETS any recorded approvals — the operators approved a
    specific population (its fingerprint is stored on the preview and
    re-checked at start), so a new preview voids their sign-off.
    """
    from apps.people.models_school_batch import SchoolTransferBatch

    if batch.status not in (
        SchoolTransferBatch.Status.DRAFT,
        SchoolTransferBatch.Status.PREVIEWED,
        # Re-preview from APPROVED is the recovery path when the population
        # diverged after sign-off (start refuses on fingerprint mismatch).
        SchoolTransferBatch.Status.APPROVED,
    ):
        raise BatchBlockedError(f"cannot preview from {batch.status!r}")

    covered = _already_covered_pks(batch)
    eligible = list(
        eligible_student_qs(batch).values_list("pk", "first_name", "last_name")
    )
    to_move = [row for row in eligible if str(row[0]) not in covered]
    approvals_reset = bool(
        batch.approved_by_primary_id or batch.approved_by_secondary_id
    )
    batch.preview = {
        "eligible": len(eligible),
        "already_in_flight_or_moved": len(eligible) - len(to_move),
        "to_move": len(to_move),
        "pks_sha256": _population_fingerprint(row[0] for row in to_move),
        "consent_mode": batch.consent_mode,
        "sample": [
            {"pk": str(pk), "name": f"{first} {last}".strip()}
            for pk, first, last in to_move[:10]
        ],
        "domains": _batch_domains(batch),
        "generated_at": timezone.now().isoformat(),
    }
    if approvals_reset:
        batch.approved_by_primary = None
        batch.approved_by_secondary = None
        batch.save(
            update_fields=[
                "preview",
                "approved_by_primary",
                "approved_by_secondary",
                "updated_at",
            ]
        )
    else:
        batch.save(update_fields=["preview", "updated_at"])
    note = f"{len(to_move)} student(s) to move ({len(eligible)} eligible)"
    if approvals_reset:
        note += " — prior approvals reset by re-preview"
    batch.advance(SchoolTransferBatch.Status.PREVIEWED, note=note)
    return batch.preview


def record_batch_approval(batch, actor, confirm_slug: str) -> dict[str, Any]:
    """Purge-grammar dual approval: two DISTINCT staff operators, each retyping
    the source school's slug. First call journals the primary approver; the
    second (different) operator completes the approval. The primary slot is
    claimed with an atomic conditional UPDATE so two racing first-approvers
    can never overwrite each other."""
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
    if not int((batch.preview or {}).get("to_move") or 0):
        raise BatchBlockedError(
            "preview shows nothing to move — approving an empty batch is refused "
            "(fix the cohort, or there is no merge to run)"
        )

    claimed = SchoolTransferBatch.objects.filter(  # tenant-isolation-allow: operator-plane-batch-approval-atomic-claim-by-pk
        pk=batch.pk, approved_by_primary__isnull=True
    ).update(approved_by_primary=actor)
    if claimed:
        batch.refresh_from_db()
        batch.advance(
            SchoolTransferBatch.Status.PREVIEWED,
            note=f"primary approval by {getattr(actor, 'username', '')}"[:200],
        )
        return {"approved": False, "awaiting": "secondary approver"}

    batch.refresh_from_db()
    if batch.status != SchoolTransferBatch.Status.PREVIEWED:
        raise BatchBlockedError(f"cannot approve from {batch.status!r} — preview first")
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
    """Fan out one TransferCase per eligible student; batch → RUNNING.

    Single-flighted (two operators double-clicking Start must not double-fan),
    and the live population is fingerprint-checked against the approved
    preview — enrolment churn between approval and start forces a re-preview
    (which resets approvals) instead of silently moving a different set.
    """
    from django.core.cache import cache

    lock_key = f"rmc-school-batch-start-{batch.pk}"
    if not cache.add(lock_key, "1", timeout=600):  # magic-number-allow: single-flight-lock-ttl-seconds
        raise BatchBlockedError("a start is already in flight for this batch")
    try:
        return _start_batch_locked(batch, actor=actor)
    finally:
        cache.delete(lock_key)


def _start_batch_locked(batch, *, actor) -> dict[str, Any]:
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    batch.refresh_from_db()
    if batch.status != SchoolTransferBatch.Status.APPROVED:
        raise BatchBlockedError(f"cannot start from {batch.status!r}")

    preview = batch.preview or {}
    institutional = (
        batch.consent_mode == SchoolTransferBatch.ConsentMode.INSTITUTIONAL
    )
    # The mode the operators approved is frozen on the preview — a batch whose
    # consent_mode changed after approval must not start (a per-guardian batch
    # silently flipped to institutional would bypass guardian consent).
    if preview.get("consent_mode") != batch.consent_mode:
        raise BatchBlockedError(
            "consent mode changed since preview/approval — re-preview and re-approve"
        )
    if institutional and not (batch.consent_basis or "").strip():
        raise BatchBlockedError(
            "institutional mode requires a recorded consent_basis"
        )

    covered = _already_covered_pks(batch)
    profiles = [
        p for p in eligible_student_qs(batch) if str(p.pk) not in covered
    ]
    fingerprint = _population_fingerprint(p.pk for p in profiles)
    if not preview.get("pks_sha256") or preview["pks_sha256"] != fingerprint:
        raise BatchBlockedError(
            "the eligible population changed since approval — re-preview "
            "(which resets approvals) and re-approve the new set"
        )

    domains = _batch_domains(batch)
    created = 0
    for profile in profiles:
        # Atomic per student: a crash mid-fan-out never leaves a case below
        # APPROVED (the advancer also heals any legacy stragglers).
        with transaction.atomic():
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

    skipped = int(preview.get("already_in_flight_or_moved") or 0)
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
    """Run up to ``max_cases`` APPROVED cases; roll up and maybe complete.

    The lock TTL must exceed the worst-case chunk runtime (each case is a
    full export + apply, minutes each) — an expired lock would let a second
    advancer interleave and clobber the ledger (D.1 audit finding).
    """
    from django.core.cache import cache

    lock_key = f"rmc-school-batch-run-{batch.pk}"
    if not cache.add(lock_key, "1", timeout=3600):  # magic-number-allow: single-flight-lock-ttl-covers-worst-case-chunk-seconds
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

    _reap_stale_compensating(batch)
    _heal_interrupted_fanout(batch)

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


def _reap_stale_compensating(batch) -> None:
    """A crash between COMPENSATING and FAILED strands the case forever
    (COMPENSATING→FAILED is its only legal exit and nothing re-drives it) —
    and with it the whole batch. Reap after the threshold."""
    from apps.people.models_transfer import TransferCase, TransferStateError

    cutoff = timezone.now() - timedelta(seconds=REAP_COMPENSATING_AFTER_SECONDS)
    stale = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
        batch=batch,
        status=TransferCase.Status.COMPENSATING,
        updated_at__lt=cutoff,
    )
    for case in stale:
        try:
            case.advance(
                TransferCase.Status.FAILED,
                note="stale compensation reaped by the batch advancer",
            )
        except TransferStateError:  # pragma: no cover — raced by a live compensator
            continue


def _heal_interrupted_fanout(batch) -> None:
    """Institutional cases left below APPROVED by an interrupted start are
    covered-but-never-runnable (the covered set skips them, the advancer only
    runs APPROVED) — re-advance them instead of stranding the batch."""
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase, TransferStateError

    if batch.consent_mode != SchoolTransferBatch.ConsentMode.INSTITUTIONAL:
        return
    stragglers = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
        batch=batch,
        status__in=(
            TransferCase.Status.DRAFT,
            TransferCase.Status.CONSENT_PENDING,
        ),
    )
    for case in stragglers:
        try:
            if case.status == TransferCase.Status.DRAFT:
                case.advance(
                    TransferCase.Status.CONSENT_PENDING,
                    note=f"institutional consent basis on batch {batch.pk}",
                )
            case.advance(
                TransferCase.Status.APPROVED,
                note="re-advanced after interrupted institutional fan-out",
            )
        except TransferStateError:  # pragma: no cover — raced by a concurrent healer
            continue


def _maybe_complete(batch, ledger) -> dict[str, Any]:
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    # D.1: re-read the truth before completing. An operator cancel that landed
    # while this advance was running must WIN — advance() trusts the in-memory
    # status, so completing off a stale RUNNING would overwrite CANCELLED.
    batch.refresh_from_db()
    if batch.status != SchoolTransferBatch.Status.RUNNING:
        return {"status": batch.status, "open": 0, "runnable_left": 0,
                "succeeded": 0, "issues": 0}

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
    # APPLIED means applied-but-parity-unverified (reconcile below threshold
    # parks there for operator review) — honest completion counts it as an
    # issue, not a clean success.
    unreconciled = cases.filter(status=TransferCase.Status.APPLIED).count()
    issues = (
        cases.filter(
            status__in=(TransferCase.Status.FAILED, TransferCase.Status.CANCELLED)
        ).count()
        + len(exhausted)
        + unreconciled
    )
    succeeded = cases.filter(status=TransferCase.Status.RECONCILED).count()

    if open_count == 0 and runnable_left == 0:
        target = (
            SchoolTransferBatch.Status.COMPLETED
            if issues == 0
            else SchoolTransferBatch.Status.COMPLETED_WITH_ISSUES
        )
        batch.completed_at = timezone.now()
        batch.save(update_fields=["completed_at", "updated_at"])
        note = f"{succeeded} reconciled, {issues} issue(s)"
        if unreconciled:
            note += f" ({unreconciled} applied but parity-unverified)"
        batch.advance(target, note=note)
    return {
        "status": batch.status,
        "open": open_count,
        "runnable_left": runnable_left,
        "succeeded": succeeded,
        "issues": issues,
    }


def cancel_batch(batch, *, actor=None, note: str = "") -> None:
    """Stop the batch: no further scheduling. In-flight cases finish their own
    FSM; already-opened APPROVED cases stay for the single-case console.
    Takes the run lock so a cancel can never interleave with (and be
    overwritten by) an in-flight advance."""
    from django.core.cache import cache

    from apps.people.models_school_batch import SchoolTransferBatch

    lock_key = f"rmc-school-batch-run-{batch.pk}"
    if not cache.add(lock_key, "1", timeout=3600):  # magic-number-allow: single-flight-lock-ttl-covers-worst-case-chunk-seconds
        raise BatchBlockedError(
            "an advance is in flight for this batch — retry the cancel shortly"
        )
    try:
        batch.refresh_from_db()
        batch.advance(
            SchoolTransferBatch.Status.CANCELLED,
            note=(note or f"cancelled by {getattr(actor, 'username', '')}")[:200],
        )
    finally:
        cache.delete(lock_key)
    _audit(batch, actor, "batch cancelled")


def wind_down_source(batch, *, actor, confirm_slug: str) -> dict[str, Any]:
    """Merge handoff (DR5): portability export + lifecycle deactivate of the
    source. Refuses while any case is unfinished OR while any enrollable
    student remains active at the source (late enrollees, cohort-excluded or
    consent-declined students must never be stranded at a dead tenant).
    ALUMNI records deliberately stay with the source — they are history, not
    enrollable students; the export carries them. NEVER purges."""
    from django.core.cache import cache

    lock_key = f"rmc-school-batch-winddown-{batch.pk}"
    if not cache.add(lock_key, "1", timeout=1800):  # magic-number-allow: single-flight-lock-ttl-seconds
        raise BatchBlockedError("a wind-down is already in flight for this batch")
    try:
        return _wind_down_source_locked(
            batch, actor=actor, confirm_slug=confirm_slug
        )
    finally:
        cache.delete(lock_key)


def _wind_down_source_locked(batch, *, actor, confirm_slug: str) -> dict[str, Any]:
    from apps.people.models import StudentProfile
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.models_transfer import TransferCase

    batch.refresh_from_db()
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
    # "applied" (parity-unverified) and "approved" (never ran / blocked) both
    # block — deactivating under a half-verified or unmoved student is the
    # exact leak this guard exists for.
    unfinished = TransferCase.objects.filter(  # tenant-isolation-allow: transfer-case-cross-tenant-by-design-batch-fk-scoped
        batch=batch,
        status__in=_OPEN_CASE_STATUSES + ("approved", "applied"),
    ).count()
    if unfinished:
        raise BatchBlockedError(
            f"{unfinished} case(s) still unfinished — resolve or abort them first"
        )
    # Whole-school honesty check, independent of the batch's cohort: ANY
    # enrollable student still active at the source refuses the wind-down.
    remaining = (
        StudentProfile.objects.filter(
            school=batch.source_school, is_active=True, merged_into__isnull=True
        )
        .exclude(
            status__in=[
                StudentProfile.Status.TRANSFERRED,
                StudentProfile.Status.ALUMNI,
            ]
        )
        .count()
    )
    if remaining:
        raise BatchBlockedError(
            f"{remaining} active student(s) remain at the source school and "
            "would be stranded — transfer or archive them before wind-down"
        )
    alumni_remaining = StudentProfile.objects.filter(
        school=batch.source_school,
        is_active=True,
        status=StudentProfile.Status.ALUMNI,
    ).count()

    from apps.schools.tenant_offboarding import (
        run_wind_down_deactivate,
        run_wind_down_export,
    )

    export = run_wind_down_export(batch.source_school, full=True, actor=actor)
    run_wind_down_deactivate(batch.source_school, actor=actor)
    batch.wind_down = {
        "export_zip": export.export_zip_path,
        "student_export_count": export.student_export_count,
        "alumni_remaining": alumni_remaining,
        "deactivated": True,
        "at": timezone.now().isoformat(),
        "by": getattr(actor, "pk", None),
    }
    batch.save(update_fields=["wind_down", "updated_at"])
    batch.history = [
        *(batch.history or []),
        {
            "note": (
                "source wound down (export + deactivate); "
                f"{alumni_remaining} alumni record(s) stay with the source; "
                "purge stays in the offboarding console"
            ),
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
        except Exception:  # noqa: BLE001 — one broken batch must not starve the rest of the tick
            logger.exception("school_batch.advance_failed batch=%s", batch.pk)
            outcomes.append({"batch": str(batch.pk), "error": "advance failed"})
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
    "REAP_COMPENSATING_AFTER_SECONDS",
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
