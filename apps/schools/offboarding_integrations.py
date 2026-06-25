"""Best-effort integration teardown before tenant purge."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def teardown_integrations_for_offboarding(school) -> dict[str, Any]:
    """Revoke/disconnect external integrations; never raises."""
    result: dict[str, Any] = {
        "marketplace_disconnected": 0,
        "migration_tokens_revoked": 0,
        "errors": [],
    }
    school_id = getattr(school, "pk", None)
    if not school_id:
        return result

    try:
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        qs = ServiceIntegration.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-offboarding-teardown
            school_id=school_id,
            is_active=True,
        )
        result["marketplace_disconnected"] = qs.update(is_active=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("offboarding marketplace disconnect failed: %s", exc)
        result["errors"].append(f"marketplace:{type(exc).__name__}")

    try:
        from apps.migration_cloud.models import MigrationCloudAPIToken

        tokens = MigrationCloudAPIToken.objects.filter(  # tenant-isolation-allow: explicit-tenant-scoped-token-revoke
            tenant_scope_id=school_id,
            revoked_at__isnull=True,
        )
        from django.utils import timezone

        now = timezone.now()
        count = tokens.update(revoked_at=now)
        result["migration_tokens_revoked"] = count
    except Exception as exc:  # noqa: BLE001
        logger.warning("offboarding migration token revoke failed: %s", exc)
        result["errors"].append(f"migration_tokens:{type(exc).__name__}")

    return result


def external_refs_for_purge_preview(school) -> dict[str, Any]:
    """Non-DB external refs surfaced in dry-run (Stripe pending, integrations)."""
    refs: dict[str, Any] = {"remote_pending_stripe": [], "active_connectors": 0}
    try:
        from apps.billing.models import TenantSubscription

        for sub in TenantSubscription.objects.filter(school_id=school.pk).exclude(
            status="canceled"
        ):
            ref = (sub.external_subscription_ref or "").strip()
            if ref:
                refs["remote_pending_stripe"].append(ref)
    except Exception:
        pass
    try:
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        refs["active_connectors"] = ServiceIntegration.objects.filter(
            school_id=school.pk,
            is_active=True,
        ).count()
    except Exception:
        pass
    return refs
