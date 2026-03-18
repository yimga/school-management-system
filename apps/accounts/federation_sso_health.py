"""Wedge 45: IdP / federation login health (last success, failures) for operator visibility."""

from __future__ import annotations

import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def record_sso_success(integration_id: int) -> None:
    """Call after successful SAML ACS or OIDC callback login."""
    try:
        from apps.accounts.models import FederationSsoHealth

        h, _ = FederationSsoHealth.objects.get_or_create(
            service_integration_id=integration_id
        )
        FederationSsoHealth.objects.filter(pk=h.pk).update(
            last_success_at=timezone.now(),
            success_count=F("success_count") + 1,
        )
    except Exception:
        logger.exception("record_sso_success failed integration_id=%s", integration_id)


def record_sso_failure(integration_id: int, reason: str = "") -> None:
    """Call on SAML/OIDC callback errors (tenant-visible IdP health)."""
    if not integration_id:
        return
    try:
        from apps.accounts.models import FederationSsoHealth

        summary = (reason or "error")[:380]
        h, _ = FederationSsoHealth.objects.get_or_create(
            service_integration_id=integration_id
        )
        FederationSsoHealth.objects.filter(pk=h.pk).update(
            last_failure_at=timezone.now(),
            last_error_summary=summary,
            failure_count=F("failure_count") + 1,
        )
    except Exception:
        logger.exception("record_sso_failure failed integration_id=%s", integration_id)
