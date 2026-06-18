"""Custom domain wizard → DNS verification + OSS edge TLS bootstrap.

Open-source deployment path: **Caddy** or **nginx** + **Let's Encrypt** (ACME),
with **dnspython** for TXT verification. Cloudflare Workers / paid edge vendors
are optional — not required for tenant custom domains.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def schedule_dns_check(*, school: Any, domain: str) -> dict[str, Any]:
    """Ensure ``SchoolDomain`` exists and queue asynchronous TXT verification.

    Edge TLS provisioning uses the platform domain sync layer once verification
    succeeds (``sync_verified_schooldomain`` → Caddy/nginx + Let's Encrypt).
    """
    from apps.schools.domain_sync import normalize_domain
    from apps.schools.models import SchoolDomain

    if school is None or not domain:
        return {"ok": False, "error": "missing_school_or_domain"}

    hostname = normalize_domain(domain.strip())
    if not hostname:
        return {"ok": False, "error": "invalid_domain"}

    obj, created = SchoolDomain.objects.get_or_create(
        school=school,
        domain=hostname,
        defaults={
            "kind": SchoolDomain.Kind.CUSTOM,
            "is_verified": False,
        },
    )

    result = {
        "ok": True,
        "domain_id": str(obj.pk),
        "domain": obj.domain,
        "created": created,
        "dns_token": str(obj.dns_token),
        "scheduled_at": timezone.now().isoformat(),
    }

    try:
        from apps.siteconfig.tasks_custom_domain import verify_custom_domain_task

        verify_custom_domain_task.delay(int(obj.pk))
        result["async"] = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("custom_domain async verify skipped, trying inline: %s", exc)
        from apps.schools.dns_verification import verify_and_activate_schooldomain

        verified = verify_and_activate_schooldomain(obj)
        result["async"] = False
        result["verified"] = bool(verified)

    logger.info(
        "custom_domain.schedule_dns_check school=%s domain=%s created=%s",
        getattr(school, "pk", None),
        hostname,
        created,
    )
    return result
