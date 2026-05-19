"""Celery tasks for social feed sync and outbox processing."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.social_media.models import SocialPostOutbox
from apps.social_media.services import aggregator, publisher

logger = logging.getLogger(__name__)


@shared_task(name="social_media.sync_tenant_feeds")
def sync_tenant_feeds(school_id: str | None = None, platform: bool = False) -> int:
    count = 0
    if platform:
        aggregator.aggregate_scope_feeds(platform_scope=True)
        return 1
    if school_id:
        aggregator.aggregate_scope_feeds(school_id=school_id)
        return 1
    return count


@shared_task(name="social_media.process_outbox_batch")
def process_outbox_batch(limit: int = 25) -> int:
    processed = 0
    rows = (
        SocialPostOutbox.objects.filter(status="pending")
        .select_related("integration")
        .order_by("priority", "created_at")[:limit]
    )
    for row in rows:
        row.status = "processing"
        row.save(update_fields=["status"])
        publisher.process_outbox_row(row)
        processed += 1
    return processed
