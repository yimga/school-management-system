"""Third-party social API adapters (isolated per integration)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class ProviderRateLimitError(Exception):
    """HTTP 429 or provider-specific throttle."""

    status_code = 429


class ProviderTokenExpiredError(Exception):
    """OAuth token rejected — tenant must re-authenticate."""

    status_code = 401


class ProviderNotConfiguredError(Exception):
    """No usable token — skip live fetch, use cache only."""


@dataclass
class ProviderPostResult:
    external_id: str
    provider: str


def fetch_feed_items(integration) -> list[dict[str, Any]]:
    """
    Poll provider for timeline items.

    Production deployments wire real HTTP clients per provider. When tokens
    are absent or expired, raises typed errors so the aggregator can degrade
    to ``feed_cache_json``.
    """
    token = (integration.encrypted_oauth_token or "").strip()
    if not token:
        raise ProviderNotConfiguredError("missing_oauth_token")
    if integration.token_expired():
        raise ProviderTokenExpiredError("token_expired")

    # Provider HTTP is env-gated — without SOCIAL_LIVE_FETCH=1 we treat as configured
    # but return an empty delta so cache remains authoritative until keys are provisioned.
    from django.conf import settings

    if not getattr(settings, "SOCIAL_LIVE_FETCH_ENABLED", False):
        return []

    # Placeholder for live provider SDK/HTTP — never log token material.
    logger.info(
        "social_provider_fetch_skipped_live",
        extra={"provider": integration.provider, "integration_id": str(integration.id)},
    )
    return []


def publish_post(integration, *, body: str, media_urls: list[str] | None = None) -> ProviderPostResult:
    token = (integration.encrypted_oauth_token or "").strip()
    if not token:
        raise ProviderNotConfiguredError("missing_oauth_token")
    if integration.token_expired():
        raise ProviderTokenExpiredError("token_expired")

    from django.conf import settings

    if not getattr(settings, "SOCIAL_LIVE_PUBLISH_ENABLED", False):
        # Deterministic id for dry-run / staging without external API.
        return ProviderPostResult(
            external_id=f"dry-run-{integration.provider}-{timezone.now().timestamp():.0f}",
            provider=integration.provider,
        )

    logger.info(
        "social_provider_publish_skipped_live",
        extra={"provider": integration.provider, "integration_id": str(integration.id)},
    )
    return ProviderPostResult(
        external_id=f"queued-{integration.provider}-{timezone.now().timestamp():.0f}",
        provider=integration.provider,
    )
