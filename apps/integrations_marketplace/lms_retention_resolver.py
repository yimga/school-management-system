"""v4.00.83 — Resolve retention years for a tenant+table combination.

Lookup precedence (per memo on this wave):
  1. TenantRetentionOverride row
  2. Env RMC_LMS_RETENTION_<TABLE>_YEARS
  3. Default 7 years (FERPA)

The resolver NEVER raises — DB unavailability returns the env/default.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)


DEFAULT_RETENTION_YEARS = 7


_TARGET_TABLE_ENV_KEYS = {
    "lms_diag_action_audit": "RMC_LMS_RETENTION_DIAG_ACTION_AUDIT_YEARS",
    "lms_push_grade_audit": "RMC_LMS_RETENTION_PUSH_GRADE_AUDIT_YEARS",
    "lms_token_rotation_chain": "RMC_LMS_RETENTION_TOKEN_ROTATION_CHAIN_YEARS",
    "webhook_dead_letter": "RMC_LMS_RETENTION_WEBHOOK_DEAD_LETTER_YEARS",
}


def resolve_retention_years(*, tenant_schema: str, target_table: str) -> int:
    """Return effective retention years for (tenant, table). Never raises.

    Returns 0 to mean "retain forever" (caller honors that)."""
    # Precedence 1: tenant override
    try:
        from apps.integrations_marketplace.models import TenantRetentionOverride
        row = TenantRetentionOverride.objects.filter(
            tenant_schema=tenant_schema, target_table=target_table,
        ).only("retention_years").first()
        if row is not None:
            return int(row.retention_years)
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention override lookup failed: %s", exc)

    # Precedence 2: env override
    env_key = _TARGET_TABLE_ENV_KEYS.get(target_table)
    if env_key:
        env_val = os.environ.get(env_key, "")
        if env_val:
            try:
                return max(0, int(env_val))
            except (TypeError, ValueError):
                pass

    return DEFAULT_RETENTION_YEARS


def set_tenant_retention_override(*, tenant_schema: str, target_table: str, retention_years: int, reason: str = "", set_by_actor_id: str = "") -> object | None:
    """Create or update a TenantRetentionOverride. Returns the row, or None on failure.

    v4.00.87: after a successful write, defensively emit a retention-floor
    escalation alert if the override sits below the regulatory floor. The
    alert emission NEVER breaks the override write (broad try/except)."""
    try:
        from apps.integrations_marketplace.models import TenantRetentionOverride
        clamped_years = max(0, int(retention_years))
        row, _created = TenantRetentionOverride.objects.update_or_create(
            tenant_schema=tenant_schema[:64], target_table=target_table[:64],
            defaults={
                "retention_years": clamped_years,
                "reason": (reason or "")[:256],
                "set_by_actor_id": (set_by_actor_id or "")[:64],
            },
        )
        # v4.00.87: defensive alert emission on below-floor override writes.
        try:
            from apps.integrations_marketplace.retention_escalation_alerts import (
                check_override_below_floor,
            )
            check_override_below_floor(
                tenant_schema=tenant_schema[:64],
                target_table=target_table[:64],
                retention_years=clamped_years,
            )
        except Exception as alert_exc:  # noqa: BLE001
            logger.debug("retention floor alert emission failed: %s", alert_exc)
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("tenant retention override write failed: %s", exc)
        return None
