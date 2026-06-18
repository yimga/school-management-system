"""Safeguarding background privilege audit — Celery beat sweep."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="safeguarding.audit_privilege_context", bind=True, ignore_result=False)
def audit_privilege_context_task(self) -> dict:
    """Scan active admin memberships; flag expired credentials in tenant settings."""
    from apps.schools.models import School, SchoolMembership

    cutoff = timezone.now() - timedelta(hours=24)
    flagged = 0
    scanned = 0
    for school in School.objects.filter(is_active=True).only("id", "settings")[:500]:
        scanned += 1
        settings = dict(school.settings or {})
        sg = dict(settings.get("safeguarding") or {})
        inbox = list(sg.get("dsl_inbox") or [])
        stale_roles = (
            SchoolMembership.objects.filter(
                school=school,
                role__in=("ADMIN", "IT_ADMIN"),  # role-string-allow: registry-backed SchoolMembership.role values (no enum; see schools.models._get_role_choices)
                user__last_login__isnull=False,
                user__last_login__lt=cutoff,
            ).count()
        )
        if stale_roles:
            inbox.append(
                {
                    "ts": timezone.now().isoformat(),
                    "kind": "privilege.stale_admin_login",
                    "count": stale_roles,
                }
            )
            sg["dsl_inbox"] = inbox[-200:]  # magic-number-allow: DSL inbox retention cap (most recent 200 entries)
            sg["last_privilege_audit_at"] = timezone.now().isoformat()
            settings["safeguarding"] = sg
            school.settings = settings
            school.save(update_fields=["settings"])
            flagged += 1
    return {"ok": True, "schools_scanned": scanned, "schools_flagged": flagged}
