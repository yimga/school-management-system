"""Custom-domain teardown on tenant deactivation (reversible).

When a school is switched off, its white-label custom domain(s) must stop
resolving to live tenant content — otherwise a deactivated tenant keeps a
working hostname (customer confusion + a routing-layer liability). This is the
deprovision counterpart to ``dns_verification`` / ``domain_sync``.

Deactivation is REVERSIBLE (the platform's soft-delete philosophy), so this only
*suspends* routing: it marks the tenant's CUSTOM ``SchoolDomain`` rows unverified
and clears ``School.custom_domain_verified`` while KEEPING the rows and the
``custom_domain`` string, so a later reactivation can re-run DNS verification.
Permanent purge already drops these rows via the ``School`` CASCADE, so no
separate "release" path is needed here.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def unbind_custom_domains(school, *, actor=None, reason: str = "") -> dict[str, Any]:
    """Suspend routing for every verified CUSTOM domain bound to ``school``.

    Reversible: rows and the ``custom_domain`` string are retained so a later
    reactivation can re-verify. Idempotent — a second call finds nothing still
    verified and is a no-op. Returns a summary dict.
    """
    from apps.schools.models import SchoolDomain, SchoolProvisioningEvent

    verified_custom = SchoolDomain.objects.filter(
        school=school,
        kind=SchoolDomain.Kind.CUSTOM,
        is_verified=True,
    )
    suspended = [entry.domain for entry in verified_custom]
    if suspended:
        verified_custom.update(is_verified=False, verified_at=None)

    school_changed: list[str] = []
    if getattr(school, "custom_domain_verified", False):
        school.custom_domain_verified = False
        school_changed.append("custom_domain_verified")
    if school_changed:
        school.save(update_fields=school_changed + ["updated_at"])

    if suspended or school_changed:
        try:
            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.DOMAIN_UNVERIFIED,
                status=SchoolProvisioningEvent.Status.WARNING,
                message="Custom domain routing suspended on deactivation.",
                payload={
                    "suspended_domains": suspended,
                    "reason": str(reason or "")[:200],
                    "reversible": True,
                },
                created_by=actor,
            )
        except Exception:  # noqa: BLE001 - audit logging must never break lifecycle
            logger.warning(
                "unbind_custom_domains: provisioning event log failed for school=%s",
                getattr(school, "pk", None),
            )

    return {"suspended_domains": suspended, "verified_cleared": bool(school_changed)}
