"""Purge orchestration: resumable state machine + session/token revocation.

These compose with the EXISTING purge command (apps/schools/tenant_offboarding.py
``apply_purge``) — wire by calling ``begin_purge_operation`` at the start,
``mark_purge_phase`` after each step, ``revoke_all_sessions_for_school`` before
schema drop, and ``complete_purge_operation`` at the end (which signs the
certificate). A purge interrupted mid-run leaves a RUNNING PurgeOperation whose
``completed_phases`` lets a re-run skip finished work (``needs_resume``).
"""

from __future__ import annotations

import logging

from django.db import IntegrityError
from django.utils import timezone

from apps.compliance.models_audit import AuditLog
from apps.lifecycle.models_purge import PurgeOperation
from apps.lifecycle.purge_certificate import (
    build_certificate_payload,
    sign_deletion_certificate,
)

logger = logging.getLogger(__name__)

_REVOKE_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def _audit(op, *, actor, action, reason) -> None:
    try:
        AuditLog.objects.create(
            user=actor if getattr(actor, "pk", None) else None,
            action=action,
            model_name="PurgeOperation",
            object_id=str(op.id or ""),
            object_repr=str(op)[:500],
            app_label="lifecycle",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
            new_values={
                "school_id": op.school_id,
                "school_slug": op.school_slug,
                "status": op.status,
                "completed_phases": list(op.completed_phases or []),
            },
            reason=str(reason)[:255],
        )
    except Exception:  # noqa: BLE001 — audit best-effort, never breaks the purge
        logger.warning("PurgeOperation audit failed", exc_info=True)


def find_resumable(*, school_id) -> PurgeOperation | None:
    """The latest non-terminal purge for a school, if any (for resume)."""
    return (
        PurgeOperation.objects.filter(
            school_id=str(school_id),
            status__in=PurgeOperation.RESUMABLE_STATUSES,
        )
        .order_by("-created_at")
        .first()
    )


def begin_purge_operation(
    *, school_id, school_slug, actor=None, reason=""
) -> PurgeOperation:
    """Start (or resume) a purge. Reuses a resumable row if one exists."""
    existing = find_resumable(school_id=school_id)
    if existing is not None:
        existing.mark_running()
        existing.save(update_fields=["status", "started_at", "updated_at"])
        _audit(
            existing,
            actor=actor,
            action=AuditLog.Action.UPDATE,
            reason="Purge operation resumed",
        )
        return existing
    try:
        op = PurgeOperation.objects.create(
            school_id=str(school_id),
            school_slug=str(school_slug)[:255],
            requested_by=actor,
            reason=(reason or "")[:255],
            status=PurgeOperation.Status.RUNNING,
            started_at=timezone.now(),
        )
    except IntegrityError:
        # Raced with a concurrent purge of the same school — the partial-unique
        # constraint (one non-terminal op per school) rejected the duplicate.
        # Reuse the winner's row instead of minting a second certificate.
        existing = find_resumable(school_id=school_id)
        if existing is not None:
            existing.mark_running()
            existing.save(update_fields=["status", "started_at", "updated_at"])
            return existing
        raise
    _audit(
        op,
        actor=actor,
        action=AuditLog.Action.CREATE,
        reason="Purge operation started",
    )
    return op


def mark_purge_phase(op, phase) -> PurgeOperation:
    """Record a completed phase (idempotent) for resumability."""
    op.add_phase(phase)
    op.save(update_fields=["completed_phases", "updated_at"])
    return op


def fail_purge_operation(op, error) -> PurgeOperation:
    op.mark_failed(str(error))
    op.save(update_fields=["status", "last_error", "updated_at"])
    _audit(
        op,
        actor=None,
        action=AuditLog.Action.UPDATE,
        reason="Purge operation failed",
    )
    return op


def complete_purge_operation(
    *, op, row_total=0, schema_dropped=False, manifest_path="", sessions_revoked=0
) -> PurgeOperation:
    """Finalize the purge and sign the deletion certificate."""
    op.row_total = int(row_total or 0)
    op.schema_dropped = bool(schema_dropped)
    op.manifest_path = (manifest_path or "")[:512]
    op.sessions_revoked = int(sessions_revoked or 0)
    op.mark_completed()
    payload = build_certificate_payload(op)
    op.certificate = payload
    op.certificate_signature = sign_deletion_certificate(payload)
    op.certificate_signed_at = timezone.now()
    op.save()
    _audit(
        op,
        actor=op.requested_by,
        action=AuditLog.Action.DELETE,
        reason="Tenant purge completed; deletion certificate signed",
    )
    return op


def revoke_all_sessions_for_school(*, school_id, user_ids) -> int:
    """Invalidate every Django session + offline token/device for a tenant's users.

    Sessions aren't indexed by user, so we scan unexpired sessions and match the
    authenticated user id — acceptable for a purge (rare, offline). Best-effort:
    a failure in one revocation path never blocks the others or the purge.
    """
    uid_list = [u for u in (user_ids or []) if u is not None]
    uid_set = {str(u) for u in uid_list}
    revoked = 0
    if uid_set:
        try:
            from django.contrib.sessions.models import Session

            for s in Session.objects.filter(expire_date__gte=timezone.now()):
                try:
                    if str(s.get_decoded().get("_auth_user_id")) in uid_set:
                        s.delete()
                        revoked += 1
                except Exception:  # noqa: BLE001 — one bad session row never blocks
                    continue
        except _REVOKE_ERRORS:
            logger.warning("session revocation failed", exc_info=True)

    # Offline capability tokens + registered devices.
    for model_path in (
        ("apps.accounts.models_offline_device", "OfflineCapabilityToken"),
        ("apps.accounts.models_offline_device", "DeviceRegistration"),
    ):
        try:
            mod = __import__(model_path[0], fromlist=[model_path[1]])
            model = getattr(mod, model_path[1])
            model.objects.filter(
                user_id__in=uid_list, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
        except _REVOKE_ERRORS:
            logger.info("offline token/device revoke skipped", exc_info=True)
        except Exception:  # noqa: BLE001 — field/model variance never blocks purge
            logger.info("offline token/device revoke variance", exc_info=True)

    return revoked
