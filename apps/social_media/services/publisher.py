"""Multi-channel cross-posting for admissions, athletics, and milestones."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.social_media.models import SocialMediaIntegration, SocialPostOutbox, SocialPostPriority
from apps.social_media.scope import assert_integration_access, integration_scope_key
from apps.social_media.services import providers, throttle
from apps.social_media.services.asset_processor import resize_for_provider

logger = logging.getLogger(__name__)


def enqueue_cross_post(
    request,
    *,
    body: str,
    providers: list[str] | None = None,
    media_urls: list[str] | None = None,
    source: str = "workflow",
) -> list[SocialPostOutbox]:
    """
    Queue outbound posts to all active integrations for the request tenant.

    ``providers`` limits to a subset of SocialProvider values.
    """
    school = getattr(request, "school", None)
    if school is None:
        qs = SocialMediaIntegration.objects.filter(is_active=True, school__isnull=True)
    else:
        qs = SocialMediaIntegration.objects.filter(is_active=True, school=school)
    if providers:
        qs = qs.filter(provider__in=providers)

    user = getattr(request, "user", None)
    actor_id = str(getattr(user, "pk", "") or "")
    rows: list[SocialPostOutbox] = []
    media = list(media_urls or [])

    with transaction.atomic():
        for integration in qs:
            assert_integration_access(request, integration, action="publish")
            processed_media = [
                resize_for_provider(url, integration.provider) for url in media
            ]
            row = SocialPostOutbox.objects.create(
                school=school,
                integration=integration,
                created_by=user if getattr(user, "is_authenticated", False) else None,
                body=body,
                media_urls=processed_media,
                priority=SocialPostPriority.STANDARD,
                status="pending",
            )
            integration.append_audit(
                actor_id=actor_id or "system",
                action="post.enqueued",
                detail={"source": source, "outbox_id": str(row.id)},
            )
            rows.append(row)
    return rows


def process_outbox_row(row: SocialPostOutbox) -> dict[str, Any]:
    integration = row.integration
    scope = integration_scope_key(integration)

    if not throttle.try_consume(scope, integration.provider, cost=2.0):
        row.status = "throttled"
        row.save(update_fields=["status"])
        return {"ok": False, "reason": "local_throttle"}

    try:
        result = providers.publish_post(
            integration,
            body=row.body,
            media_urls=row.media_urls or [],
        )
        row.status = "posted"
        row.external_post_id = result.external_id
        row.processed_at = timezone.now()
        row.save(update_fields=["status", "external_post_id", "processed_at"])
        return {"ok": True, "external_id": result.external_id}
    except providers.ProviderRateLimitError:
        row.status = "throttled"
        row.save(update_fields=["status"])
        return {"ok": False, "reason": "provider_rate_limit"}
    except providers.ProviderTokenExpiredError:
        integration.needs_reauth = True
        integration.save(update_fields=["needs_reauth", "updated_at"])
        row.status = "failed"
        row.error_code = "token_expired"
        row.processed_at = timezone.now()
        row.save(update_fields=["status", "error_code", "processed_at"])
        return {"ok": False, "reason": "token_expired"}
    except providers.ProviderNotConfiguredError:
        row.status = "failed"
        row.error_code = "not_configured"
        row.processed_at = timezone.now()
        row.save(update_fields=["status", "error_code", "processed_at"])
        return {"ok": False, "reason": "not_configured"}
