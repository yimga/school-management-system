"""Celery tasks for social feed sync and outbox processing."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.social_media.models import SocialMediaIntegration, SocialPostOutbox
from apps.social_media.services import aggregator, publisher

logger = logging.getLogger(__name__)

# How long a worker may hold a row in 'processing' before another sweep may
# assume it died and take the row back. Generous relative to one provider call.
OUTBOX_LEASE_SECONDS = 300


@shared_task(name="social_media.sync_tenant_feeds")
def sync_tenant_feeds(school_id: str | None = None, platform: bool = False) -> int:
    """Refresh ``feed_cache_json`` for one scope, or for EVERY scope when called bare.

    The no-argument call used to fall through to ``return 0`` having done nothing,
    so the obvious scheduler entry (a beat/registry row with no kwargs -- the only
    shape a scheduler can express without knowing tenant ids) was a silent no-op.
    Since ``SocialFeedAPI`` deliberately reads only the cache, "nothing ran" and
    "the campus has posted nothing" are indistinguishable on screen. Bare now means
    fan out: the platform scope plus every school that actually has an active
    integration (driving off the integration table rather than the school table so
    a campus with nothing connected costs no provider calls).
    """
    if platform:
        aggregator.aggregate_scope_feeds(platform_scope=True)
        return 1
    if school_id:
        aggregator.aggregate_scope_feeds(school_id=school_id)
        return 1

    synced = 0
    if SocialMediaIntegration.objects.filter(is_active=True, school__isnull=True).exists():
        aggregator.aggregate_scope_feeds(platform_scope=True)
        synced += 1
    # tenant-isolation-allow: celery-feed-sync-fans-out-per-school-scope
    school_ids = (
        SocialMediaIntegration.objects.filter(is_active=True, school__isnull=False)
        .values_list("school_id", flat=True)
        .distinct()
    )
    for scoped_school_id in school_ids:
        aggregator.aggregate_scope_feeds(school_id=scoped_school_id)
        synced += 1
    return synced


def _reap_abandoned_processing_rows(now) -> int:
    """Return rows whose worker never came back to 'pending'.

    ``process_outbox_batch`` stamps 'processing' and saves BEFORE calling the
    publisher, so a worker killed mid-row (or a request that timed out) left the
    row in 'processing' with no reaper anywhere -- another terminal state reached
    by accident. The lease stamp written alongside the status is what makes the
    row recoverable.
    """
    stale_unstamped = now - timedelta(seconds=OUTBOX_LEASE_SECONDS)
    return (
        SocialPostOutbox.objects.filter(status="processing")
        .filter(
            Q(next_attempt_at__lte=now)
            | Q(next_attempt_at__isnull=True, created_at__lte=stale_unstamped)
        )
        .update(status="pending", next_attempt_at=None)
    )


@shared_task(name="social_media.process_outbox_batch")
def process_outbox_batch(limit: int = 25) -> int:
    processed = 0
    now = timezone.now()
    reaped = _reap_abandoned_processing_rows(now)
    if reaped:
        logger.warning("social_outbox_reaped_abandoned_rows", extra={"count": reaped})
    # tenant-isolation-allow: celery-outbox-sweep-processes-pending-rows-per-integration
    rows = (
        SocialPostOutbox.objects.filter(
            Q(status="pending")
            | Q(status="throttled", next_attempt_at__isnull=True)
            | Q(status="throttled", next_attempt_at__lte=now)
        )
        .select_related("integration")
        .order_by("priority", "created_at")[:limit]
    )
    for row in rows:
        row.status = "processing"
        # Lease the row so a dead worker's rows come back on a later sweep.
        row.next_attempt_at = now + timedelta(seconds=OUTBOX_LEASE_SECONDS)
        row.save(update_fields=["status", "next_attempt_at"])
        publisher.process_outbox_row(row)
        processed += 1
    return processed
