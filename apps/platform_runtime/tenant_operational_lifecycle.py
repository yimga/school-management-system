"""
Operational tenant lifecycle — conception through deletion certificate.

Complements product lifecycle states in ``tenant_lifecycle_state_machine`` (demo,
paying, churned) with school-operating states used by Setup Studio, manifest
compilation, and customer-success surfaces.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Public operational contract (moderator program P1-W1.2)
STATE_CONCEPTION = "conception"
STATE_PROVISIONING = "provisioning"
STATE_COUNTRY_SETUP = "country_setup"
STATE_SETUP_STUDIO = "setup_studio"
STATE_LAUNCH_READINESS = "launch_readiness"
STATE_DAILY_OPERATIONS = "daily_operations"
STATE_ACADEMIC_YEAR_CLOSE = "academic_year_close"
STATE_RENEWAL = "renewal"
STATE_SUSPENSION = "suspension"
STATE_READ_ONLY = "read_only"
STATE_EXPORT = "export"
STATE_OFFBOARDING = "offboarding"
STATE_PURGE_SCHEDULED = "purge_scheduled"
STATE_DELETION_CERTIFICATE = "deletion_certificate"

ALL_OPERATIONAL_STATES: tuple[str, ...] = (
    STATE_CONCEPTION,
    STATE_PROVISIONING,
    STATE_COUNTRY_SETUP,
    STATE_SETUP_STUDIO,
    STATE_LAUNCH_READINESS,
    STATE_DAILY_OPERATIONS,
    STATE_ACADEMIC_YEAR_CLOSE,
    STATE_RENEWAL,
    STATE_SUSPENSION,
    STATE_READ_ONLY,
    STATE_EXPORT,
    STATE_OFFBOARDING,
    STATE_PURGE_SCHEDULED,
    STATE_DELETION_CERTIFICATE,
)

# States that must have at least one resolver emission site (verifier-enforced).
REQUIRED_OPERATIONAL_STATES: tuple[str, ...] = ALL_OPERATIONAL_STATES

# The words a school reads. ``operational_lifecycle_strip.html`` renders this
# state on tenant pages, and until 2026-08-22 it did so with ``|cut:"_"`` --
# which DELETES the separator, so a school in daily operation was told its
# lifecycle was "dailyoperations". Casing was never the fix: "Conception" is
# no more meaningful to a head teacher than "conception". These are curated,
# translated sentences, kept HERE rather than in the template so that adding a
# 15th state without adding its label is a diff a reviewer sees --
# ``scripts/scan_raw_token_in_ui.py`` reports the gap, and
# ``test_display_labels_2026_08_22`` fails on it.
OPERATIONAL_STATE_LABELS: dict[str, Any] = {
    STATE_CONCEPTION: _("Being created"),
    STATE_PROVISIONING: _("Being provisioned"),
    STATE_COUNTRY_SETUP: _("Country setup"),
    STATE_SETUP_STUDIO: _("Setup in progress"),
    STATE_LAUNCH_READINESS: _("Getting ready to launch"),
    STATE_DAILY_OPERATIONS: _("Day-to-day operations"),
    STATE_ACADEMIC_YEAR_CLOSE: _("Closing the academic year"),
    STATE_RENEWAL: _("Up for renewal"),
    STATE_SUSPENSION: _("Suspended"),
    STATE_READ_ONLY: _("Read-only"),
    STATE_EXPORT: _("Preparing your export"),
    STATE_OFFBOARDING: _("Offboarding"),
    STATE_PURGE_SCHEDULED: _("Data purge scheduled"),
    STATE_DELETION_CERTIFICATE: _("Deleted — certificate issued"),
}


def operational_state_label(state: object) -> str:
    """School-readable label for an operational lifecycle state.

    An unknown state is humanized rather than dropped: a strange label is
    recoverable, a blank chip is not. Returns ``""`` only for an empty state,
    which the strip template already treats as "render nothing".
    """
    from apps.platform_runtime.display_labels import label_for

    return label_for(OPERATIONAL_STATE_LABELS, state)

ALLOWED_OPERATIONAL_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_CONCEPTION: frozenset(
        {STATE_PROVISIONING, STATE_COUNTRY_SETUP, STATE_OFFBOARDING}
    ),
    STATE_PROVISIONING: frozenset(
        {STATE_COUNTRY_SETUP, STATE_SETUP_STUDIO, STATE_OFFBOARDING, STATE_SUSPENSION}
    ),
    STATE_COUNTRY_SETUP: frozenset(
        {STATE_SETUP_STUDIO, STATE_LAUNCH_READINESS, STATE_OFFBOARDING}
    ),
    STATE_SETUP_STUDIO: frozenset(
        {STATE_LAUNCH_READINESS, STATE_DAILY_OPERATIONS, STATE_OFFBOARDING}
    ),
    STATE_LAUNCH_READINESS: frozenset(
        {STATE_DAILY_OPERATIONS, STATE_SETUP_STUDIO, STATE_OFFBOARDING}
    ),
    STATE_DAILY_OPERATIONS: frozenset(
        {
            STATE_ACADEMIC_YEAR_CLOSE,
            STATE_RENEWAL,
            STATE_SUSPENSION,
            STATE_READ_ONLY,
            STATE_EXPORT,
            STATE_OFFBOARDING,
        }
    ),
    STATE_ACADEMIC_YEAR_CLOSE: frozenset(
        {STATE_DAILY_OPERATIONS, STATE_RENEWAL, STATE_OFFBOARDING}
    ),
    STATE_RENEWAL: frozenset(
        {STATE_DAILY_OPERATIONS, STATE_SUSPENSION, STATE_OFFBOARDING}
    ),
    STATE_SUSPENSION: frozenset(
        {STATE_READ_ONLY, STATE_DAILY_OPERATIONS, STATE_OFFBOARDING}
    ),
    STATE_READ_ONLY: frozenset({STATE_EXPORT, STATE_OFFBOARDING, STATE_DAILY_OPERATIONS}),
    STATE_EXPORT: frozenset({STATE_OFFBOARDING, STATE_PURGE_SCHEDULED}),
    STATE_OFFBOARDING: frozenset({STATE_PURGE_SCHEDULED, STATE_EXPORT}),
    STATE_PURGE_SCHEDULED: frozenset({STATE_DELETION_CERTIFICATE}),
    STATE_DELETION_CERTIFICATE: frozenset(),
}


def validate_operational_transition(from_state: str, to_state: str) -> bool:
    a = str(from_state or "").strip().lower()
    b = str(to_state or "").strip().lower()
    if a not in ALLOWED_OPERATIONAL_TRANSITIONS or b not in ALL_OPERATIONAL_STATES:
        return False
    return b in ALLOWED_OPERATIONAL_TRANSITIONS[a]


def _school_country_code(school: Any) -> str:
    getter = getattr(school, "canonical_country_code", None)
    if isinstance(getter, str) and getter.strip():
        return getter.strip().upper()[:2]
    return str(getattr(school, "country_code", "") or "").strip().upper()[:2]


def _is_offboarding(school: Any) -> bool:
    if not school:
        return False
    if getattr(school, "is_active", True) is False:
        return True
    settings = getattr(school, "settings", None) or {}
    if isinstance(settings, dict):
        if settings.get("offboarding_status") in {"started", "export_ready", "purged"}:
            return True
        if settings.get("lifecycle") == "offboarding":
            return True
    return False


def _is_suspended(school: Any) -> bool:
    try:
        from apps.billing.models import TenantSubscription

        sub = (
            TenantSubscription.objects.filter(school_id=getattr(school, "id", None))
            .order_by("-updated_at")
            .first()
        )
        if sub and str(getattr(sub, "status", "")).upper() in {
            TenantSubscription.Status.SUSPENDED,
            TenantSubscription.Status.PAST_DUE,
        }:
            return True
    except Exception:
        pass
    return bool(getattr(school, "billing_suspended", False))


def resolve_operational_lifecycle_state(school: Any) -> dict[str, Any]:
    """
    Map existing school signals to the operational lifecycle state contract.
    Read-only; safe for dashboards and manifest compilation.
    """
    if school is None:
        return {
            "state": STATE_CONCEPTION,
            "reasons": ["no_school"],
            "resolved_at": timezone.now().isoformat(),
        }

    reasons: list[str] = []
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}

    if settings.get("deletion_certificate_issued_at"):
        return {
            "state": STATE_DELETION_CERTIFICATE,
            "reasons": ["deletion_certificate_issued"],
            "resolved_at": timezone.now().isoformat(),
        }
    if settings.get("purge_scheduled_at"):
        return {
            "state": STATE_PURGE_SCHEDULED,
            "reasons": ["purge_scheduled"],
            "resolved_at": timezone.now().isoformat(),
        }
    if _is_offboarding(school):
        if settings.get("offboarding_export_ready"):
            return {
                "state": STATE_EXPORT,
                "reasons": ["offboarding_export_ready"],
                "resolved_at": timezone.now().isoformat(),
            }
        return {
            "state": STATE_OFFBOARDING,
            "reasons": ["offboarding_active"],
            "resolved_at": timezone.now().isoformat(),
        }
    if _is_suspended(school):
        if settings.get("read_only_mode"):
            reasons.append("read_only_mode")
            return {
                "state": STATE_READ_ONLY,
                "reasons": reasons or ["suspended_read_only"],
                "resolved_at": timezone.now().isoformat(),
            }
        return {
            "state": STATE_SUSPENSION,
            "reasons": ["billing_suspended"],
            "resolved_at": timezone.now().isoformat(),
        }

    try:
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        prov = resolve_provisioning_progress(school)
        if prov and prov.get("status") not in {"completed", "complete", "done"}:
            pct = prov.get("percent_complete") or prov.get("progress_percent") or 0
            if int(pct) < 100:
                return {
                    "state": STATE_PROVISIONING,
                    "reasons": ["provisioning_in_progress"],
                    "provisioning_percent": int(pct),
                    "resolved_at": timezone.now().isoformat(),
                }
    except Exception:
        pass

    cc = _school_country_code(school)
    if not cc:
        return {
            "state": STATE_COUNTRY_SETUP,
            "reasons": ["country_code_missing"],
            "resolved_at": timezone.now().isoformat(),
        }

    from apps.schools.setup_health import setup_health_score

    health = setup_health_score(school)
    score = int(health.get("score") or 0)
    if score < 60:
        return {
            "state": STATE_SETUP_STUDIO,
            "reasons": ["setup_health_below_launch_threshold"],
            "launch_readiness_score": score,
            "resolved_at": timezone.now().isoformat(),
        }
    if score < 85:
        return {
            "state": STATE_LAUNCH_READINESS,
            "reasons": ["setup_health_launch_band"],
            "launch_readiness_score": score,
            "resolved_at": timezone.now().isoformat(),
        }

    try:
        from apps.academics.year_close import academic_year_close_in_progress

        if academic_year_close_in_progress(school):
            return {
                "state": STATE_ACADEMIC_YEAR_CLOSE,
                "reasons": ["academic_year_close_active"],
                "launch_readiness_score": score,
                "resolved_at": timezone.now().isoformat(),
            }
    except Exception:
        pass

    if settings.get("renewal_window_open"):
        return {
            "state": STATE_RENEWAL,
            "reasons": ["renewal_window"],
            "launch_readiness_score": score,
            "resolved_at": timezone.now().isoformat(),
        }

    return {
        "state": STATE_DAILY_OPERATIONS,
        "reasons": ["healthy_active_tenant"],
        "launch_readiness_score": score,
        "resolved_at": timezone.now().isoformat(),
    }


__all__ = [
    "ALL_OPERATIONAL_STATES",
    "ALLOWED_OPERATIONAL_TRANSITIONS",
    "REQUIRED_OPERATIONAL_STATES",
    "STATE_ACADEMIC_YEAR_CLOSE",
    "STATE_CONCEPTION",
    "STATE_COUNTRY_SETUP",
    "STATE_DAILY_OPERATIONS",
    "STATE_DELETION_CERTIFICATE",
    "STATE_EXPORT",
    "STATE_LAUNCH_READINESS",
    "STATE_OFFBOARDING",
    "STATE_PROVISIONING",
    "STATE_PURGE_SCHEDULED",
    "STATE_READ_ONLY",
    "STATE_RENEWAL",
    "STATE_SETUP_STUDIO",
    "STATE_SUSPENSION",
    "validate_operational_transition",
    "resolve_operational_lifecycle_state",
]
