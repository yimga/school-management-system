"""Auto-record lifecycle stages from existing platform signals.

Two passive listeners:
1. School.post_save (created=True) → REQUESTED then PROVISIONED.
   The wizard creates the School row at the very end of its async
   pipeline, so by the time post_save fires we can record both stages
   in sequence (REQUESTED captures the funnel-side intent, PROVISIONED
   the actual schema landing).
2. SchoolProvisioningEvent.post_save → MIGRATING / OFFBOARDING_* mirrors.
   The provisioning event taxonomy already has the right verbs; we
   simply translate them onto the lifecycle vocabulary.

Both are best-effort: a logging failure must never break the wizard
or provisioning pipeline.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="schools.School")
def school_post_save_record_lifecycle(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .services import record_stage
        from .models import SchoolLifecycleStage

        record_stage(
            instance,
            SchoolLifecycleStage.Stage.REQUESTED,
            note="School row created",
            payload={"source": "schools.post_save"},
        )
        record_stage(
            instance,
            SchoolLifecycleStage.Stage.PROVISIONED,
            note="Schema landed",
            payload={"source": "schools.post_save"},
        )
        # Wave L5: auto-launch migration if intent was set at create time.
        # ensure_draft_migration_bundle is internally idempotent and
        # silent when no intent is set.
        try:
            from .services_migration import ensure_draft_migration_bundle

            ensure_draft_migration_bundle(instance)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lifecycle.migration_autolaunch_failed school_id=%s err=%s",
                getattr(instance, "id", "?"),
                type(exc).__name__,
            )
    except Exception as exc:  # noqa: BLE001 — best-effort sidecar logging
        logger.warning(
            "lifecycle.school_post_save_failed school_id=%s err=%s",
            getattr(instance, "id", "?"),
            type(exc).__name__,
        )


_PROVISIONING_EVENT_STAGE_MAP = {
    "OFFBOARDING_SELF_SERVICE_REQUESTED": "OFFBOARDING_REQUESTED",
    "OFFBOARDING_EXPORT": "OFFBOARDING_EXPORTED",
    "OFFBOARDING_AUTO_PURGE_SCHEDULED": "OFFBOARDING_GRACE",
    "OFFBOARDING_SELF_SERVICE_CANCELLED": "OFFBOARDING_CANCELLED",
    "OFFBOARDING_PURGE_COMPLETED": "OFFBOARDING_PURGED",
    "OFFBOARDING_AUTO_PURGE_EXECUTED": "OFFBOARDING_PURGED",
    "COMPLETED": "OPERATING",
    "FAILED": "FAILED",
}


@receiver(post_save, sender="schools.SchoolProvisioningEvent")
def provisioning_event_post_save_mirror(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .services import record_stage

        event_type = getattr(instance, "event_type", None)
        stage = _PROVISIONING_EVENT_STAGE_MAP.get(event_type)
        if not stage:
            return
        school = getattr(instance, "school", None)
        if not school:
            return
        record_stage(
            school,
            stage,
            note=f"Mirrored from {event_type}",
            payload={"source": "schools.SchoolProvisioningEvent", "event_type": event_type},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.provisioning_event_mirror_failed err=%s",
            type(exc).__name__,
        )
