"""Wave L4 — soft-delete + DSAR + audit-chain mirror.

Public API:
    mark_deleted(school, *, actor=None, reason='') -> School
    restore(school, *, actor=None) -> School
    is_in_grace(school) -> bool
    grace_expires_at(school) -> datetime or None
    audit_event_mirror(event) -> bool

Soft-delete writes School.deleted_at to now() and records lifecycle
stage OFFBOARDING_GRACE. The existing hard-purge path
(apps/schools/tenant_offboarding.run_scheduled_purges) is unchanged
and remains operator-gated — soft-delete just pre-stages the
deletion intent so an operator (or the school admin via DSAR
self-serve) can reverse before the grace window expires.

The audit-chain mirror writes a `MigrationCloudAuditEvent` for each
offboarding SchoolProvisioningEvent so we get hash-chain integrity
parity with Migration Cloud's audit log (closes audit gap from the
session audit).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import SchoolLifecycleStage
from .services import actor_hash, record_stage

logger = logging.getLogger(__name__)


def _grace_days() -> int:
    """Operator-configurable grace window. Default 30 days."""
    try:
        from apps.schools.tenant_offboarding_policy import auto_purge_grace_days

        days = int(auto_purge_grace_days() or 30)
    except Exception:  # noqa: BLE001
        days = 30
    return max(1, days)


def mark_deleted(school, *, actor=None, reason: str = "") -> "object":
    """Set school.deleted_at to now and record OFFBOARDING_GRACE stage."""
    if not school or not getattr(school, "id", None):
        raise ValueError("mark_deleted requires a saved School")
    with transaction.atomic():
        if school.deleted_at is None:
            school.deleted_at = timezone.now()
            school.is_active = False
            school.save(update_fields=["deleted_at", "is_active"])
        record_stage(
            school,
            SchoolLifecycleStage.Stage.OFFBOARDING_GRACE,
            actor=actor,
            note=(reason or "")[:200],
            payload={
                "source": "lifecycle.mark_deleted",
                "grace_days": _grace_days(),
                "deleted_at_iso": school.deleted_at.isoformat() if school.deleted_at else None,
            },
        )
    return school


def restore(school, *, actor=None) -> "object":
    """Clear deleted_at and record OFFBOARDING_CANCELLED on the timeline."""
    if not school or not getattr(school, "id", None):
        raise ValueError("restore requires a saved School")
    with transaction.atomic():
        # Refuse if school was already hard-purged (PURGED is terminal).
        already_purged = SchoolLifecycleStage.objects.filter(
            school=school, stage=SchoolLifecycleStage.Stage.OFFBOARDING_PURGED
        ).exists()
        if already_purged:
            raise ValueError("school is already purged — restore is irreversible past PURGED")
        if school.deleted_at is not None:
            school.deleted_at = None
            school.save(update_fields=["deleted_at"])
        record_stage(
            school,
            SchoolLifecycleStage.Stage.OFFBOARDING_CANCELLED,
            actor=actor,
            note="Soft-delete restored",
            payload={"source": "lifecycle.restore"},
        )
    return school


def is_in_grace(school) -> bool:
    """True iff school.deleted_at is set AND grace window has not expired."""
    if not school:
        return False
    deleted_at: Optional[datetime] = getattr(school, "deleted_at", None)
    if deleted_at is None:
        return False
    return timezone.now() < deleted_at + timedelta(days=_grace_days())


def grace_expires_at(school) -> Optional[datetime]:
    """Return when the grace window closes, or None if not soft-deleted."""
    if not school:
        return None
    deleted_at: Optional[datetime] = getattr(school, "deleted_at", None)
    if deleted_at is None:
        return None
    return deleted_at + timedelta(days=_grace_days())


# Audit-chain mirror to MigrationCloudAuditEvent.
# Closes audit gap: SchoolProvisioningEvent is mutable Django model
# with no hash-chain. We piggy-back on Migration Cloud's already-
# tamper-evident MigrationCloudAuditEvent so offboarding events get
# the same forensic guarantees.

_OFFBOARDING_AUDIT_EVENT_TYPES = frozenset(
    {
        "OFFBOARDING_EXPORT",
        "OFFBOARDING_DEACTIVATED",
        "OFFBOARDING_PURGE_REQUESTED",
        "OFFBOARDING_PURGE_COMPLETED",
        "OFFBOARDING_SELF_SERVICE_REQUESTED",
        "OFFBOARDING_SELF_SERVICE_CANCELLED",
        "OFFBOARDING_AUTO_PURGE_SCHEDULED",
        "OFFBOARDING_AUTO_PURGE_EXECUTED",
    }
)


# Audit-chain mirror to MigrationCloudAuditEvent. v3.61.6 Wave L6:
# the enum was extended with 4 lifecycle.offboarding.* values via
# migration migration_cloud.0029, so we can now do a first-class
# tamper-evident mirror with hash-chain integrity.
#
# The original SchoolProvisioningEvent rows remain the canonical
# record; the mirror is forensic parity with Migration Cloud's
# audit log. audit_event_log_mirror below stays as a structured-log
# backstop for environments where Migration Cloud isn't loaded.


_SCHOOL_EVENT_TO_AUDIT_TYPE = {
    "OFFBOARDING_EXPORT": "lifecycle.offboarding.export",
    "OFFBOARDING_DEACTIVATED": "lifecycle.offboarding.deactivated",
    "OFFBOARDING_PURGE_REQUESTED": "lifecycle.offboarding.purge_requested",
    "OFFBOARDING_PURGE_COMPLETED": "lifecycle.offboarding.purge_completed",
}


def audit_event_mirror(event) -> bool:
    """First-class mirror into MigrationCloudAuditEvent with hash chain.

    Returns True on successful write, False otherwise (event type not
    mirrored, Migration Cloud unavailable, or write failure).

    PII-safe: actor is hashed inside the manager.record() call; payload
    sanitizer drops 14 sensitive keys; tenant slug never persisted raw
    (only the SHA-256 prefix).
    """
    if event is None:
        return False
    event_type = getattr(event, "event_type", None)
    audit_type = _SCHOOL_EVENT_TO_AUDIT_TYPE.get(event_type)
    if not audit_type:
        return False
    school = getattr(event, "school", None)
    if school is None or not getattr(school, "slug", None):
        return False
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

        MigrationCloudAuditEvent.objects.record(
            tenant_slug=school.slug,
            event_type=audit_type,
            actor=getattr(event, "actor", None),
            subject=str(school.id),
            payload_summary={
                "lifecycle_event_id": str(getattr(event, "id", "")),
                "school_provisioning_event_type": event_type,
            },
        )
        return True
    except ImportError:
        return False
    except Exception as exc:  # noqa: BLE001 — never break the request path
        logger.warning(
            "lifecycle.audit_event_mirror.failed event_id=%s err=%s",
            getattr(event, "id", "?"),
            type(exc).__name__,
        )
        return False


def audit_event_log_mirror(event) -> bool:
    """Structured-log mirror of offboarding events.

    PII-safe: actor_id is SHA-256-prefix-hashed; never raw email/name.
    """
    if event is None:
        return False
    event_type = getattr(event, "event_type", None)
    if event_type not in _OFFBOARDING_AUDIT_EVENT_TYPES:
        return False
    school = getattr(event, "school", None)
    actor = getattr(event, "actor", None)
    logger.info(
        "lifecycle.offboarding.audit event_id=%s school_id=%s school_slug=%s event_type=%s actor_hash=%s created_at=%s",
        getattr(event, "id", ""),
        getattr(school, "id", "") if school else "",
        getattr(school, "slug", "") if school else "",
        event_type,
        actor_hash(actor),
        getattr(event, "created_at", ""),
    )
    notify_offboarding_confirmed(event)
    return True


def notify_offboarding_confirmed(event) -> bool:
    """Send the GDPR offboarding-confirmation email (audit H11).

    Fires on the DEACTIVATED / purge-requested transitions — the points at
    which the tenant admin's address is still reachable (after the actual
    purge their email is gone). Publishes ``tenant.offboarding.confirmed`` to
    the platform Email Matrix. Best-effort: never breaks the offboarding flow.
    """
    confirm_event_types = {
        "OFFBOARDING_DEACTIVATED",
        "OFFBOARDING_PURGE_REQUESTED",
        "OFFBOARDING_AUTO_PURGE_SCHEDULED",
    }
    if getattr(event, "event_type", None) not in confirm_event_types:
        return False
    school = getattr(event, "school", None)
    if school is None:
        return False
    # Capture the admin address NOW (before purge wipes it).
    admin_email = ""
    verification = getattr(school, "signupverification", None)
    if verification is not None:
        admin_email = getattr(verification, "email", "") or ""
    try:
        from apps.platform_runtime.event_bus import publish_event

        publish_event(
            "tenant.offboarding.confirmed",
            {
                "school_name": getattr(school, "name", "")
                or getattr(school, "slug", ""),
                "admin_email": admin_email,
                "grace_days": _grace_days(),
            },
            school_id=getattr(school, "id", None),
            idempotency_key=f"offboard_confirmed:{getattr(school, 'id', '')}",
        )
        return True
    except Exception:  # noqa: BLE001 — mail never breaks offboarding
        logger.warning(
            "lifecycle.offboarding.confirm_email_publish_failed school_id=%s",
            getattr(school, "id", None),
        )
        return False
