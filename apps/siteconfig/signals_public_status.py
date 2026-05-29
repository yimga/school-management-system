"""v4.00.45+v4.00.49 — Notify confirmed multi-channel subscribers on incident change.

Wired by ``apps.siteconfig.apps.SiteconfigConfig.ready``. The signal fires for
both inserts (newly-promoted incidents) and updates (status flip from
INVESTIGATING → IDENTIFIED → MONITORING → RESOLVED).

v4.00.49 routes each row through
``apps.siteconfig.notifications_public_status.dispatch_to_subscriber`` so SMS
/ Slack / Discord rows fan out alongside the original email rows.

Idempotency: each subscriber receives one notification per public-incident
state transition; ``last_alerted_at`` enforces "at most one per N seconds per
subscriber" as a safety belt against rapid status flips.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


_NOTIFICATION_MIN_INTERVAL_SECONDS = 30


def _notify_subscribers(incident, kind: str) -> None:
    from apps.siteconfig.models_feature_controls import PublicIncidentSubscription
    from apps.siteconfig.notifications_public_status import dispatch_to_subscriber

    try:
        from django.conf import settings
        from django.urls import reverse
    except ImportError:
        return

    now = timezone.now()
    threshold = now - timedelta(seconds=_NOTIFICATION_MIN_INTERVAL_SECONDS)
    subscribers = list(
        PublicIncidentSubscription.objects.filter(
            confirmed_at__isnull=False,
            unsubscribed_at__isnull=True,
        ).exclude(last_alerted_at__gt=threshold)[:5000]
    )
    if not subscribers:
        return

    site_origin = getattr(settings, "PUBLIC_STATUS_SITE_ORIGIN", "") or ""
    status_url = f"{site_origin}/status/" if site_origin else "/status/"

    for sub in subscribers:
        try:
            unsub_path = reverse("public_status_unsubscribe", args=[sub.unsubscribe_token])
            unsub_url = f"{site_origin}{unsub_path}" if site_origin else unsub_path
            result = dispatch_to_subscriber(
                sub,
                incident,
                kind,
                status_url=status_url,
                unsub_url=unsub_url,
            )
            if result.ok:
                sub.last_alerted_at = now
                sub.save(update_fields=["last_alerted_at", "updated_at"])
        except Exception:  # noqa: BLE001 — best-effort; never break the signal
            logger.debug("public_status: per-subscriber dispatch failed", exc_info=True)


def _connect_public_incident_signals() -> None:
    """Idempotent connect — apps.ready may run more than once under tests."""
    from apps.siteconfig.models_feature_controls import PublicIncident

    @receiver(post_save, sender=PublicIncident, weak=False, dispatch_uid="public_incident_fanout")
    def _on_public_incident_saved(sender, instance, created, **kwargs):
        kind = "incident opened" if created else "incident updated"
        try:
            _notify_subscribers(instance, kind)
        except Exception:  # noqa: BLE001 — never break the save
            logger.debug("public_status: notify_subscribers raised", exc_info=True)
