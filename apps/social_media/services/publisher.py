"""Multi-channel cross-posting for admissions, athletics, and milestones."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.social_media.models import SocialMediaIntegration, SocialPostOutbox, SocialPostPriority
from apps.social_media.scope import (
    assert_integration_access,
    integration_scope_key,
    queryset_for_scope,
    resolve_feed_scope,
)
from apps.social_media.services import providers, throttle
from apps.social_media.services.asset_processor import resize_for_provider

logger = logging.getLogger(__name__)

# A rate limit is a "come back later", not a "give up". Back off, then stop trying
# so a permanently-refused row cannot spin forever.
MAX_DELIVERY_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = (30, 120, 600, 1800)


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

    SCOPE IS RESOLVED, NOT INFERRED. This used to read a missing ``request.school``
    as "platform scope" and select ``school__isnull=True`` -- the COMPANY's own
    X/Instagram/LinkedIn/Facebook accounts. Any authenticated request that reached
    this code without a tenant bound (a host the tenant middleware does not resolve,
    a shared-cookie session on the base domain) therefore failed OPEN onto the
    corporate accounts. ``resolve_feed_scope`` + ``queryset_for_scope`` are the
    fail-CLOSED pair the README prescribes: platform scope only when the host
    affirmatively says so, otherwise ``.none()`` for the ambiguous case.
    """
    school, platform_scope = resolve_feed_scope(request)
    qs = queryset_for_scope(
        SocialMediaIntegration.objects.filter(is_active=True),
        school=school,
        platform_scope=platform_scope,
    )
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


def _defer_for_retry(row: SocialPostOutbox, *, reason: str) -> bool:
    """Park a rate-limited row for a later sweep, or fail it once attempts run out.

    'throttled' used to be TERMINAL. The drainer selected ``status="pending"``
    only, nothing anywhere moved a row back, and the throttle is easy to trip
    (30 tokens per scope+provider, 2.0 spent per post -- so the 16th post in a
    scope is stamped and abandoned). The caller already had its 202, so the post
    simply never went out and nothing recorded why. Returns True if the row will
    be retried, False if it has been failed for good.
    """
    row.attempts = (row.attempts or 0) + 1
    if row.attempts >= MAX_DELIVERY_ATTEMPTS:
        row.status = "failed"
        row.error_code = f"{reason}_exhausted"
        row.processed_at = timezone.now()
        row.next_attempt_at = None
        row.save(
            update_fields=["attempts", "status", "error_code", "processed_at", "next_attempt_at"]
        )
        return False
    backoff = RETRY_BACKOFF_SECONDS[min(row.attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
    row.status = "throttled"
    row.error_code = reason
    row.next_attempt_at = timezone.now() + timedelta(seconds=backoff)
    row.save(update_fields=["attempts", "status", "error_code", "next_attempt_at"])
    return True


def process_outbox_row(row: SocialPostOutbox) -> dict[str, Any]:
    integration = row.integration
    scope = integration_scope_key(integration)

    if not throttle.try_consume(scope, integration.provider, cost=2.0):
        retrying = _defer_for_retry(row, reason="local_throttle")
        return {"ok": False, "reason": "local_throttle", "retrying": retrying}

    try:
        result = providers.publish_post(
            integration,
            body=row.body,
            media_urls=row.media_urls or [],
        )
        row.status = "posted"
        row.external_post_id = result.external_id
        row.processed_at = timezone.now()
        row.next_attempt_at = None
        row.save(
            update_fields=["status", "external_post_id", "processed_at", "next_attempt_at"]
        )
        return {"ok": True, "external_id": result.external_id}
    except providers.ProviderRateLimitError:
        retrying = _defer_for_retry(row, reason="provider_rate_limit")
        return {"ok": False, "reason": "provider_rate_limit", "retrying": retrying}
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
