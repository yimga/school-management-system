"""Transfer case execution — the Wave B go-live engine (design §5).

``run_transfer_case`` drives one APPROVED case end-to-end:

    export (build sealed envelope) → envelope_sealed → applying
    (real migration-cloud apply at the target) → passport link +
    source retirement → applied → reconcile → reconciled

Every transition is journaled on the case; failures compensate honestly
(``applying`` failures roll the case through ``compensating`` → ``failed``
and best-effort-roll-back the bundle's migration runs). The offline-pending
guard refuses to export while the student's device still holds undrained
queued writes at the source school — replay after a school change hits the
frozen-``school_id`` tenant-mismatch guards and would strand those writes.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

TRANSFER_COMPUTATION = "student.transfer"


class TransferBlockedError(RuntimeError):
    """A guard refused the transfer — the case FSM was NOT advanced."""


def offline_transfer_blockers(profile) -> list[str]:
    """Undrained offline work at the source school (design §5 step 7)."""
    if not getattr(profile, "user_id", None):
        return []
    try:
        from apps.platform_runtime.models import OfflineAction
    except ImportError:
        return []
    pending = OfflineAction.objects.filter(
        school=profile.school,
        user_id=profile.user_id,
        status__in=[
            OfflineAction.Status.QUEUED,
            OfflineAction.Status.SYNCING,
            OfflineAction.Status.FAILED,
            OfflineAction.Status.CONFLICT,
        ],
    ).count()
    if pending:
        return [
            f"{pending} offline action(s) queued/failed/conflicted at the source "
            "school — drain or resolve them before transferring"
        ]
    return []


def run_transfer_case(case, *, actor=None, off_http: bool = True) -> dict[str, Any]:
    """Execute one APPROVED transfer case. Returns a summary dict.

    Production default ``off_http=True`` stages the envelope on the caller then
    queues advance+apply on HeavyWorkOutbox; the case stays ``applying`` until
    :func:`continue_transfer_case_if_ready` (beat/periodic) finishes the FSM.
    Tests that need an inline apply pass ``off_http=False``.
    """
    from django.core.cache import cache

    lock_key = f"rmc-transfer-run-{case.pk}"
    # Single-flight: two operators clicking Run concurrently would both pass
    # the status guard (advance() trusts the in-memory instance) and drive
    # the SAME bundle from two pipelines. cache.add is the platform's
    # atomic-acquire pattern (billing lock).
    if not cache.add(lock_key, "1", timeout=600):  # magic-number-allow: single-flight-lock-ttl-seconds
        raise TransferBlockedError("a run is already in flight for this case")
    try:
        return _run_transfer_case_locked(case, actor=actor, off_http=off_http)
    finally:
        cache.delete(lock_key)


def _run_transfer_case_locked(case, *, actor=None, off_http: bool = True) -> dict[str, Any]:
    from apps.people.models import StudentProfile
    from apps.people.models_transfer import TransferCase

    case.refresh_from_db()  # the lock serializes runners; re-read the truth
    if case.status != TransferCase.Status.APPROVED:
        raise TransferBlockedError(
            f"case must be approved to run (status={case.status!r})"
        )

    profile = StudentProfile.objects.filter(
        school=case.source_school, pk=case.source_profile_pk
    ).first()
    if profile is None:
        raise TransferBlockedError("source student profile not found")
    # D.1 audit closeout: a profile another case already moved (or an operator
    # retired) must never silently fork into a second target — the second
    # transfer would re-bind the passport and duplicate the student's records
    # at a second live school.
    if profile.status == StudentProfile.Status.TRANSFERRED or not profile.is_active:
        raise TransferBlockedError(
            "source student is already transferred or retired — refusing a second move"
        )

    blockers = offline_transfer_blockers(profile)
    if blockers:
        raise TransferBlockedError("; ".join(blockers))

    from apps.interop.student_transfer_export import (
        TRANSFER_DEFAULT_DOMAINS,
        build_student_transfer_envelope,
    )
    from apps.migration_cloud.transfer_intake import ingest_transfer_envelope

    domains = tuple(case.domains or TRANSFER_DEFAULT_DOMAINS)
    case.advance(TransferCase.Status.EXPORTING)
    try:
        envelope = build_student_transfer_envelope(
            profile,
            target_school=case.target_school,
            actor_id=str(getattr(actor, "pk", "") or ""),
            domains=domains,
        )
        case.envelope_checksum = envelope.checksum
        case.domains = sorted(envelope.domain_rows.keys())
        case.save(update_fields=["envelope_checksum", "domains", "updated_at"])
        case.advance(TransferCase.Status.ENVELOPE_SEALED)
    except Exception as exc:  # noqa: BLE001 — export failure is terminal, nothing applied yet
        case.advance(TransferCase.Status.FAILED, note=f"export failed: {exc}"[:400])
        raise

    case.advance(TransferCase.Status.APPLYING)
    try:
        intake = ingest_transfer_envelope(
            envelope,
            target_school=case.target_school,
            triggered_by_id=getattr(actor, "pk", None),
            dry_run=False,
            idempotency_key=f"rmc-transfer-case-{case.pk}",
            off_http=off_http,
        )
        case.target_bundle_id = intake["bundle_id"]
        case.save(update_fields=["target_bundle_id", "updated_at"])
        if intake.get("queued"):
            case.history = [
                *(case.history or []),
                {
                    "note": (
                        f"apply queued on heavy-work outbox "
                        f"outbox_id={intake.get('outbox_id')}"
                    ),
                    "at": timezone.now().isoformat(),
                },
            ]
            case.save(update_fields=["history", "updated_at"])
            return {
                "case_id": str(case.pk),
                "status": case.status,
                "bundle_id": case.target_bundle_id,
                "queued": True,
                "durable_outbox": True,
                "outbox_id": intake.get("outbox_id"),
                "apply": intake.get("apply"),
            }
        target_profile = _link_passport_and_retire_source(case, profile, actor)
    except Exception as exc:  # noqa: BLE001 — apply failure compensates
        _compensate(case, exc)
        raise

    case.advance(TransferCase.Status.APPLIED)
    reconciled = _reconcile(case)
    _stamp_lineage(case, profile, target_profile)
    _audit(case, actor)

    summary = {
        "case_id": str(case.pk),
        "status": case.status,
        "bundle_id": case.target_bundle_id,
        "target_profile_pk": str(getattr(target_profile, "pk", "") or ""),
        "apply": intake.get("apply"),
        "reconciled": reconciled,
    }
    logger.info(
        "transfer_case.ran case=%s status=%s bundle=%s",
        case.pk,
        case.status,
        case.target_bundle_id,
        extra={"scope": "transfer_case"},
    )
    return summary


def continue_transfer_case_if_ready(case, *, actor=None) -> dict[str, Any]:
    """Advance an APPLYING case once the MC bundle has landed (async FSM).

    Returns ``{advanced: bool, status, reason?}``. Safe to call repeatedly.
    """
    from apps.migration_cloud.models import BundleStatus, MigrationBundle
    from apps.people.models import StudentProfile
    from apps.people.models_transfer import TransferCase

    case.refresh_from_db()
    if case.status != TransferCase.Status.APPLYING:
        return {
            "advanced": False,
            "status": case.status,
            "reason": "not_applying",
        }
    if not case.target_bundle_id:
        return {
            "advanced": False,
            "status": case.status,
            "reason": "missing_bundle",
        }

    # tenant-isolation-allow: transfer-continue-bundle-pk-owned-by-case-target-school
    bundle = MigrationBundle.objects.filter(pk=case.target_bundle_id).first()
    if bundle is None:
        return {
            "advanced": False,
            "status": case.status,
            "reason": "bundle_missing",
        }
    if bundle.status == BundleStatus.FAILED:
        _compensate(case, RuntimeError("migration bundle failed"))
        return {"advanced": True, "status": case.status, "reason": "bundle_failed"}
    if bundle.status not in (BundleStatus.APPLIED, BundleStatus.RECONCILED):
        return {
            "advanced": False,
            "status": case.status,
            "reason": "bundle_pending",
            "bundle_status": bundle.status,
        }

    profile = StudentProfile.objects.filter(
        school=case.source_school, pk=case.source_profile_pk
    ).first()
    if profile is None:
        case.advance(TransferCase.Status.FAILED, note="source profile missing at continue")
        return {"advanced": True, "status": case.status, "reason": "source_missing"}

    try:
        target_profile = _link_passport_and_retire_source(case, profile, actor)
        case.advance(TransferCase.Status.APPLIED)
        reconciled = _reconcile(case)
        _stamp_lineage(case, profile, target_profile)
        _audit(case, actor)
    except Exception as exc:  # noqa: BLE001
        _compensate(case, exc)
        raise

    return {
        "advanced": True,
        "status": case.status,
        "reconciled": reconciled,
        "target_profile_pk": str(getattr(target_profile, "pk", "") or ""),
    }


def continue_applying_transfers(*, limit: int = 20) -> dict[str, Any]:
    """Sweep APPLYING cases whose MC bundles finished (beat / health tick)."""
    from apps.people.models_transfer import TransferCase

    limit = max(1, min(int(limit or 20), 100))  # magic-number-allow: transfer-continue-sweep-cap
    # tenant-isolation-allow: platform-transfer-continue-sweep-by-status
    qs = list(
        TransferCase.objects.filter(status=TransferCase.Status.APPLYING)
        .exclude(target_bundle_id__isnull=True)
        .order_by("updated_at")[:limit]
    )
    advanced = 0
    pending = 0
    failed = 0
    for case in qs:
        try:
            result = continue_transfer_case_if_ready(case)
            if result.get("advanced"):
                advanced += 1
                if result.get("reason") == "bundle_failed":
                    failed += 1
            else:
                pending += 1
        except Exception:  # noqa: BLE001 — one case must not abort the sweep
            logger.exception("transfer_continue_sweep_failed case=%s", case.pk)
            failed += 1
    return {
        "scanned": len(qs),
        "advanced": advanced,
        "pending": pending,
        "failed": failed,
    }


def _apply_summary_for_bundle(bundle_id: int | None) -> dict[str, Any]:
    """Rebuild the sync-shaped apply block from bundle mapping_summary."""
    if not bundle_id:
        return {}
    try:
        from apps.migration_cloud.models import MigrationBundle

        # tenant-isolation-allow: transfer-await-apply-summary-by-case-owned-bundle-pk
        bundle = MigrationBundle.objects.filter(pk=bundle_id).only(
            "mapping_summary", "status"
        ).first()
    except Exception:  # noqa: BLE001
        return {}
    if bundle is None:
        return {}
    totals = (bundle.mapping_summary or {}).get("apply_totals") or {}
    return {
        "dry_run": bool(totals.get("dry_run", False)),
        "status": bundle.status,
        "total_created": int(totals.get("created") or 0),
        "total_updated": int(totals.get("updated") or 0),
        "total_quarantined": int(totals.get("quarantined") or 0),
    }


def run_transfer_case_await_apply(case, *, actor=None) -> dict[str, Any]:
    """Run the production async path, then drain+continue in-process.

    Prefer this in tests over ``off_http=False`` so the real outbox FSM is
    exercised while remaining TestCase-transaction-safe (no drain thread).
    """
    from unittest.mock import patch

    from apps.platform_runtime.heavy_work_outbox import drain_heavy_work_outbox

    with patch("apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain"):
        summary = run_transfer_case(case, actor=actor, off_http=True)

    if not summary.get("queued"):
        return summary

    # Same-thread drain — avoid the daemon-thread kick that cannot see TestCase rows.
    drain_heavy_work_outbox(limit=10)
    continued = continue_transfer_case_if_ready(case, actor=actor)
    case.refresh_from_db()
    apply_block = _apply_summary_for_bundle(case.target_bundle_id)
    return {
        "case_id": str(case.pk),
        "status": case.status,
        "bundle_id": case.target_bundle_id,
        "queued": False,
        "awaited": True,
        "continued": continued,
        "apply": apply_block,
        "outbox_id": summary.get("outbox_id"),
        "reconciled": case.status == "reconciled",
    }

def _link_passport_and_retire_source(case, source_profile, actor):
    """Design §5 step 5: same passport GUID at both schools; source retires."""
    from apps.interop.student_transfer_export import student_external_ref
    from apps.people.models import StudentProfile
    from apps.people.passport_services import (
        get_or_create_passport_for_student,
        link_student_to_passport,
    )

    target_profile = _resolve_target_profile(case, source_profile)
    if target_profile is None:
        raise RuntimeError(
            f"apply reported success but no target profile resolved for "
            f"ref {student_external_ref(source_profile)!r}"
        )

    passport, _created = get_or_create_passport_for_student(source_profile, actor)
    link_student_to_passport(passport, target_profile, actor)
    case.passport = passport
    case.save(update_fields=["passport", "updated_at"])

    source_profile.status = StudentProfile.Status.TRANSFERRED
    source_profile.is_active = False
    source_profile.save(update_fields=["status", "is_active"])
    return target_profile


def _resolve_target_profile(case, source_profile):
    """Id-mapping first (the pipeline's own audit trail), external ref second."""
    from apps.interop.student_transfer_export import student_external_ref
    from apps.people.models import StudentProfile

    ref = student_external_ref(source_profile)
    try:
        from apps.migration_cloud.models import MigrationIdMapping

        mapping = MigrationIdMapping.objects.filter(
            school=case.target_school,
            legacy_id=ref,
            domain="students",
        ).first()
        if mapping is not None and mapping.canonical_pk:
            found = StudentProfile.objects.filter(
                school=case.target_school, pk=mapping.canonical_pk
            ).first()
            if found is not None:
                return found
    except Exception:  # noqa: BLE001 — fall through to the direct lookup
        pass

    for field in ("admission_number", "student_code", "exam_candidate_number"):
        found = StudentProfile.objects.filter(
            school=case.target_school, **{field: ref}
        ).first()
        if found is not None:
            return found
    return None


def _compensate(case, exc) -> None:
    """Apply failed: journal, best-effort bundle rollback, land on FAILED."""
    from apps.people.models_transfer import TransferCase

    case.advance(
        TransferCase.Status.COMPENSATING, note=f"apply failed: {exc}"[:400]
    )
    try:
        from apps.automation.models import MigrationRun

        if case.target_bundle_id:
            for run in MigrationRun.objects.filter(  # tenant-isolation-allow: rollback-scoped-via-case-target-bundle-execution-summary
                execution_summary__bundle_id=case.target_bundle_id
            ):
                trigger = getattr(run, "trigger_rollback", None)
                if callable(trigger):
                    trigger()
    except Exception:  # noqa: BLE001 — compensation is best-effort
        logger.warning("transfer_case.rollback_failed case=%s", case.pk)
    case.advance(TransferCase.Status.FAILED, note="compensation complete")


def _reconcile(case) -> bool:
    """Run migration-cloud parity; only a clean pass moves the case on."""
    from apps.people.models_transfer import TransferCase

    try:
        from apps.migration_cloud.models import BundleStatus, MigrationBundle
        from apps.migration_cloud.reconciliation import reconcile_bundle

        reconcile_bundle(bundle_id=case.target_bundle_id)
        bundle = MigrationBundle.objects.filter(pk=case.target_bundle_id).only("status").first()  # tenant-isolation-allow: bundle-pk-from-own-case
        if bundle is not None and bundle.status == BundleStatus.RECONCILED:
            case.advance(TransferCase.Status.RECONCILED)
            return True
        case.history = [
            *(case.history or []),
            {
                "note": "reconciliation parity below threshold — case stays applied for operator review",
                "at": timezone.now().isoformat(),
            },
        ]
        case.save(update_fields=["history", "updated_at"])
    except Exception:  # noqa: BLE001 — reconcile is a quality gate, not a rollback trigger
        logger.warning("transfer_case.reconcile_failed case=%s", case.pk)
    return False


def _stamp_lineage(case, source_profile, target_profile) -> None:
    try:
        from apps.metadata.models_derived_lineage import record_derived_lineage

        record_derived_lineage(
            output=target_profile,
            computation=TRANSFER_COMPUTATION,
            inputs=[
                {"model": "people.StudentProfile", "pk": str(source_profile.pk)},
                {"model": "people.TransferCase", "pk": str(case.pk)},
            ],
            school=case.target_school,
            version="wave-b",
        )
    except Exception:  # noqa: BLE001 — lineage never blocks a transfer
        logger.warning("transfer_case.lineage_failed case=%s", case.pk)


def _audit(case, actor) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            user=actor if getattr(actor, "pk", None) else None,
            model_name="TransferCase",
            object_id=str(case.pk)[:200],
            object_repr=(
                f"student transfer {case.source_school_id} → {case.target_school_id} "
                f"({case.status})"
            )[:200],
            app_label="people",
            new_values={"status": case.status, "bundle_id": case.target_bundle_id},
        )
    except Exception:  # noqa: BLE001 — audit never blocks a transfer
        logger.warning("transfer_case.audit_failed case=%s", case.pk)


__all__ = [
    "TRANSFER_COMPUTATION",
    "TransferBlockedError",
    "offline_transfer_blockers",
    "run_transfer_case",
    "run_transfer_case_await_apply",
    "continue_transfer_case_if_ready",
    "continue_applying_transfers",
]
