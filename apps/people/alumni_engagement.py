"""Alumni engagement pipeline — graduation capture + Celery outreach (OSS stack)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def configure_alumni_pipeline(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist alumni program config and queue background sync."""
    if school is None:
        return {"ok": False}
    settings = dict(getattr(school, "settings", None) or {})
    alumni = dict(settings.get("alumni_engagement") or {})
    alumni.update(
        {
            "channels": payload.get("channels") or payload.get("value") or [],
            "programs": payload.get("programs") or [],
            "donation_pipeline_enabled": bool(payload.get("donation_pipeline_enabled", True)),
            "transcript_portability": bool(payload.get("transcript_portability", True)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    settings["alumni_engagement"] = alumni
    school.settings = settings
    school.save(update_fields=["settings"])

    try:
        from apps.people.tasks_alumni import sync_alumni_registry_task

        sync_alumni_registry_task.delay(int(school.pk))
    except Exception as exc:  # noqa: BLE001
        logger.debug("alumni sync enqueue skipped: %s", exc)

    return {"ok": True, "alumni_engagement": alumni}


def capture_graduation_cohort(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist graduation-capture toggles from alumni wizard step 1."""
    if school is None:
        return {"ok": False}
    settings = dict(getattr(school, "settings", None) or {})
    alumni = dict(settings.get("alumni_engagement") or {})
    alumni["graduation_capture"] = {
        k: payload.get(k)
        for k in (
            "auto_promote_alumni",
            "capture_transcript_snapshot",
            "capture_contact_on_graduation",
            "graduation_year_field",
        )
        if k in payload
    } or dict(payload)
    alumni["updated_at"] = datetime.now(timezone.utc).isoformat()
    settings["alumni_engagement"] = alumni
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "graduation_capture": alumni.get("graduation_capture")}


def snapshot_alumni_count(*, school: Any) -> int:
    from apps.people.models import StudentProfile

    return StudentProfile.objects.filter(
        school=school,
        status=StudentProfile.Status.ALUMNI,
    ).count()
