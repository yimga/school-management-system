"""Tenant reactivation engine — 4-cadence win-back ladder (v4.00.98 Phase 4).

Single public entry: :func:`run_reactivation_sweep` (idempotent).

Loop (called by Celery beat daily):

    For each cadence stage (30, 60, 90, 120):
      For each School with last_activity in the cadence window
                                    AND no prior attempt at this cadence
                                    AND is_active=True
                                    AND not is_frozen
                                    AND admin email resolvable
                                    AND admin email not unsubscribed:
        dispatch_email_for_event("tenant.reactivation.<N>d", payload)
        record TenantReactivationAttempt
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Iterable

from django.utils import timezone

logger = logging.getLogger(__name__)


_CADENCE_WINDOWS: tuple[tuple[str, int, int], ...] = (
    # (cadence_value, min_inactive_days, max_inactive_days)
    ("30d", 30, 59),
    ("60d", 60, 89),
    ("90d", 90, 119),  # magic-number-allow: reactivation-cadence-days
    ("120d", 120, 365 * 5),  # magic-number-allow: reactivation-cadence-days
)


def _hash_email(email: str) -> str:
    if not email:
        return ""
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


def _portal_url_for_reactivation(school) -> str:
    """Tenant-facing return link — never the operator manager console."""
    try:
        from apps.schools.provision_email_urls import (
            build_public_login_url,
            build_tenant_authentication_url,
            tenant_subdomain_host_exists,
        )

        if school and tenant_subdomain_host_exists(school):
            return build_tenant_authentication_url(school, "/authentication/login/")
        return build_public_login_url()
    except ImportError:
        return "https://runmycampus.com/discover/"


def _resolve_admin_email(school) -> str:
    """Best-effort recipient resolution. Prefers the verified signup email."""

    try:
        verification = getattr(school, "signupverification", None)
        if verification and getattr(verification, "email", ""):
            return str(verification.email)
    except Exception:
        pass
    # Fallback: scan School.settings['admin_email'] / ['owner_email']
    settings_blob = getattr(school, "settings", None) or {}
    for key in ("admin_email", "owner_email", "primary_email"):
        value = settings_blob.get(key)
        if value:
            return str(value)
    return ""


def _is_email_unsubscribed_marketing(email: str) -> bool:
    """Phase 3 NewsletterSubscription gate. Marketing-class unsub blocks
    win-back too because both flow through the same operator goodwill."""

    if not email:
        return False
    try:
        from apps.platform_runtime.models import (
            NewsletterSubscription,
            NewsletterSubscriptionStatus,
        )

        row = NewsletterSubscription.objects.filter(email__iexact=email).first()
        if row is None:
            return False
        return row.status == NewsletterSubscriptionStatus.UNSUBSCRIBED
    except Exception:
        return False


def _eligible_schools_for_cadence(cadence: str, min_days: int, max_days: int) -> Iterable:
    """Return the queryset of schools eligible for this cadence stage."""

    from apps.platform_runtime.models import TenantReactivationAttempt
    from apps.schools.models import School

    now = timezone.now()
    cutoff_recent = now - timedelta(days=min_days)
    cutoff_oldest = now - timedelta(days=max_days)

    # tenant-isolation-allow: platform-reactivation-scan-no-tenant-scope-required
    qs = School.objects.filter(
        is_active=True,
        is_frozen=False,
        last_activity__lt=cutoff_recent,
        last_activity__gte=cutoff_oldest,
    )
    raw_attempted = (
        # tenant-isolation-allow: platform-reactivation-log-no-tenant-scope
        TenantReactivationAttempt.objects.filter(
            cadence=cadence,
            suppressed=False,
        ).values_list("school_id", flat=True)
    )
    # School.id is UUIDField. Filter to only valid-UUID strings so legacy /
    # smoke / test rows with non-UUID school_id values do not poison the
    # exclude() with a ValidationError.
    import uuid as _uuid

    valid_uuids: set[str] = set()
    for value in raw_attempted:
        try:
            valid_uuids.add(str(_uuid.UUID(str(value))))
        except (ValueError, TypeError):
            continue
    if valid_uuids:
        qs = qs.exclude(pk__in=valid_uuids)
    return qs.order_by("last_activity")[:500]


def run_reactivation_sweep(*, dry_run: bool = False, limit_per_cadence: int = 200) -> dict:
    """Walk every cadence stage, dispatch reactivation emails for eligible
    schools, and persist TenantReactivationAttempt rows.

    Returns a per-cadence summary dict. Safe to call from CLI, beat task,
    or smoke. ``dry_run=True`` resolves recipients + would-dispatch shape
    without firing emails or persisting rows."""

    from apps.platform_runtime.models import TenantReactivationAttempt
    from apps.platform_runtime.platform_email_matrix import dispatch_email_for_event

    summary = {
        "dry_run": dry_run,
        "started_at": timezone.now().isoformat(),
        "per_cadence": {},
        "total_sent": 0,
        "total_suppressed": 0,
    }

    for cadence, min_days, max_days in _CADENCE_WINDOWS:
        rows = []
        sent = 0
        suppressed = 0
        eligible = list(_eligible_schools_for_cadence(cadence, min_days, max_days))
        for school in eligible[:limit_per_cadence]:
            admin_email = _resolve_admin_email(school)
            # v4.01 — bound suppressed rows. A suppressed school stays eligible
            # every sweep (the eligibility exclude only counts suppressed=False
            # attempts), so without this guard a NEW suppressed row was written
            # for it on every daily run, forever. Keep at most one suppressed
            # row per (school, cadence).
            if not dry_run and (not admin_email or _is_email_unsubscribed_marketing(admin_email)):
                already_suppressed = TenantReactivationAttempt.objects.filter(
                    school_id=str(school.pk), cadence=cadence, suppressed=True
                ).exists()
            else:
                already_suppressed = False
            if not admin_email:
                suppressed += 1
                if not dry_run and not already_suppressed:
                    TenantReactivationAttempt.objects.create(
                        school_id=str(school.pk),
                        school_name=getattr(school, "name", "")[:160],  # magic-number-allow: string-truncation-cap
                        cadence=cadence,
                        suppressed=True,
                        suppressed_reason="no_admin_email",
                        delivery_ok=False,
                    )
                continue
            if _is_email_unsubscribed_marketing(admin_email):
                suppressed += 1
                if not dry_run and not already_suppressed:
                    TenantReactivationAttempt.objects.create(
                        school_id=str(school.pk),
                        school_name=getattr(school, "name", "")[:160],  # magic-number-allow: string-truncation-cap
                        cadence=cadence,
                        recipient_email=admin_email[:254],  # magic-number-allow: string-truncation-cap
                        recipient_email_hash=_hash_email(admin_email),
                        suppressed=True,
                        suppressed_reason="recipient_unsubscribed",
                        delivery_ok=False,
                    )
                continue

            payload = {
                "school_name": getattr(school, "name", ""),
                "admin_email": admin_email,
                "school_id": str(school.pk),
                "portal_url": _portal_url_for_reactivation(school),
                "unsubscribe_url": _build_unsubscribe_url(admin_email),
            }
            event = f"tenant.reactivation.{cadence}"
            if dry_run:
                rows.append({"school_id": str(school.pk), "admin_email_hash": _hash_email(admin_email), "would_event": event})
                sent += 1
                continue
            try:
                result = dispatch_email_for_event(
                    event,
                    payload,
                    idempotency_key=f"reactivation:{school.pk}:{cadence}",
                )
                ok = bool(result.get("ok"))
                delivery_event_id = ""
                first_result = next(iter(result.get("results") or []), None)
                if first_result and isinstance(first_result.get("result"), dict):
                    delivery_event_id = str(first_result["result"].get("delivery_event_id") or "")
                TenantReactivationAttempt.objects.create(
                    school_id=str(school.pk),
                    school_name=getattr(school, "name", "")[:160],  # magic-number-allow: string-truncation-cap
                    cadence=cadence,
                    recipient_email=admin_email[:254],  # magic-number-allow: string-truncation-cap
                    recipient_email_hash=_hash_email(admin_email),
                    delivery_event_id=delivery_event_id[:64],
                    delivery_ok=ok,
                    delivery_error_kind=("" if ok else (result.get("reason") or "dispatch_error"))[:64],
                )
                if ok:
                    sent += 1
                else:
                    suppressed += 1
            except Exception as exc:
                logger.exception("reactivation_sweep_dispatch_failed school=%s cadence=%s", school.pk, cadence)
                suppressed += 1
                if not dry_run:
                    try:
                        TenantReactivationAttempt.objects.create(
                            school_id=str(school.pk),
                            school_name=getattr(school, "name", "")[:160],  # magic-number-allow: string-truncation-cap
                            cadence=cadence,
                            recipient_email=admin_email[:254],  # magic-number-allow: string-truncation-cap
                            recipient_email_hash=_hash_email(admin_email),
                            delivery_ok=False,
                            delivery_error_kind=f"exception:{type(exc).__name__}"[:64],
                        )
                    except Exception:
                        pass

        summary["per_cadence"][cadence] = {
            "eligible_count": len(eligible),
            "sent": sent,
            "suppressed": suppressed,
            "preview_rows": rows[:5] if dry_run else [],
        }
        summary["total_sent"] += sent
        summary["total_suppressed"] += suppressed

    summary["completed_at"] = timezone.now().isoformat()
    return summary


def _build_unsubscribe_url(email: str) -> str:
    try:
        from apps.platform_runtime.newsletter_service import (
            _build_unsubscribe_url as build,
        )

        return build(email)
    except Exception:
        return ""
