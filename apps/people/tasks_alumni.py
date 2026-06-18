"""Alumni background tasks — Celery + PostgreSQL (no paid SaaS)."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="people.sync_alumni_registry", bind=True, ignore_result=False)
def sync_alumni_registry_task(self, school_id: int) -> dict:
    from apps.people.alumni_engagement import snapshot_alumni_count
    from apps.schools.models import School

    try:
        school = School.objects.get(pk=school_id)
    except School.DoesNotExist:
        return {"ok": False, "error": "school_not_found"}

    count = snapshot_alumni_count(school=school)
    settings = dict(school.settings or {})
    alumni = dict(settings.get("alumni_engagement") or {})
    alumni["registry_count"] = count
    alumni["last_sync_at"] = __import__("django.utils.timezone", fromlist=["timezone"]).timezone.now().isoformat()
    settings["alumni_engagement"] = alumni
    school.settings = settings
    school.save(update_fields=["settings"])
    logger.info("alumni.sync school=%s count=%s", school_id, count)
    return {"ok": True, "school_id": school_id, "alumni_count": count}
