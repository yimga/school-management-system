"""Safeguarding background privilege audit — Celery beat sweep."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _is_legacy_privilege_row(row: object) -> bool:
    """A privilege-audit flag that an earlier version wrote into ``dsl_inbox``.

    Real DSL concern entries always carry an ``entry_id``; privilege flags are
    ``{ts, kind, count}`` rows with a ``kind`` and no ``entry_id``.
    """
    return (
        isinstance(row, dict)
        and not row.get("entry_id")
        and bool(row.get("kind"))
    )


@shared_task(name="safeguarding.audit_privilege_context", bind=True, ignore_result=False)
def audit_privilege_context_task(self) -> dict:
    """Scan active admin memberships; flag expired credentials in tenant settings.

    Privilege-audit flags go into their OWN ``privilege_audit_log`` bucket, never
    into ``dsl_inbox`` — that list is the DSL safeguarding-concern inbox, whose
    consumers (the operator-queue "DSL action required within KCSIE SLA" banner)
    would otherwise count these non-concern rows as open, un-acknowledgeable
    concerns forever. The sweep also self-heals any legacy privilege rows an
    earlier version left in ``dsl_inbox``, relocating them to the audit log.
    """
    from apps.schools.models import School, SchoolMembership

    cutoff = timezone.now() - timedelta(hours=24)
    flagged = 0
    scanned = 0
    healed = 0
    for school in School.objects.filter(is_active=True).only("id", "settings")[:500]:  # tenant-isolation-allow: cross-tenant-privilege-audit-sweep-each-iteration-school-scoped
        scanned += 1
        settings = dict(school.settings or {})
        sg = dict(settings.get("safeguarding") or {})
        inbox = list(sg.get("dsl_inbox") or [])
        audit_log = list(sg.get("privilege_audit_log") or [])

        # Self-heal: relocate any legacy privilege rows out of the concern inbox.
        legacy = [row for row in inbox if _is_legacy_privilege_row(row)]
        cleaned_inbox = [row for row in inbox if not _is_legacy_privilege_row(row)]

        stale_roles = (
            SchoolMembership.objects.filter(  # tenant-isolation-allow: school-scoped-via-school-kwarg-on-continuation-line
                school=school,
                role__in=("ADMIN", "IT_ADMIN"),  # role-string-allow: registry-backed SchoolMembership.role values (no enum; see schools.models._get_role_choices)
                user__last_login__isnull=False,
                user__last_login__lt=cutoff,
            ).count()
        )
        new_flag = None
        if stale_roles:
            new_flag = {
                "ts": timezone.now().isoformat(),
                "kind": "privilege.stale_admin_login",
                "count": stale_roles,
            }

        if not legacy and new_flag is None:
            continue  # nothing to write for this tenant

        audit_log.extend(legacy)
        if new_flag is not None:
            audit_log.append(new_flag)
            flagged += 1
        if legacy:
            healed += 1

        sg["dsl_inbox"] = cleaned_inbox
        sg["privilege_audit_log"] = audit_log[-200:]  # magic-number-allow: privilege-audit-log retention cap (most recent 200 entries)
        sg["last_privilege_audit_at"] = timezone.now().isoformat()
        settings["safeguarding"] = sg
        school.settings = settings
        school.save(update_fields=["settings"])
    return {
        "ok": True,
        "schools_scanned": scanned,
        "schools_flagged": flagged,
        "schools_healed": healed,
    }
