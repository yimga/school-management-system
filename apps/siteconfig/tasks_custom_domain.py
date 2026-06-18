"""Background DNS verification for custom domain wizard."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="siteconfig.verify_custom_domain", bind=True, ignore_result=False)
def verify_custom_domain_task(self, school_domain_id: int) -> dict:
    from apps.schools.dns_verification import verify_and_activate_schooldomain
    from apps.schools.models import SchoolDomain

    try:
        obj = SchoolDomain.objects.select_related("school").get(pk=school_domain_id)
    except SchoolDomain.DoesNotExist:
        return {"ok": False, "error": "domain_not_found"}

    verified = verify_and_activate_schooldomain(obj)
    return {
        "ok": True,
        "domain_id": school_domain_id,
        "domain": obj.domain,
        "verified": bool(verified),
    }


@shared_task(name="siteconfig.sweep_pending_custom_domains", bind=True, ignore_result=False)
def sweep_pending_custom_domains_task(self) -> dict:
    from apps.schools.models import SchoolDomain

    pending = (
        # tenant-isolation-allow: platform-cron-sweeps-all-pending-custom-domains
        SchoolDomain.objects.filter(is_verified=False, kind=SchoolDomain.Kind.CUSTOM)
        .order_by("created_at")[:50]
    )
    queued = 0
    for obj in pending:
        verify_custom_domain_task.delay(int(obj.pk))
        queued += 1
    return {"ok": True, "queued": queued}
