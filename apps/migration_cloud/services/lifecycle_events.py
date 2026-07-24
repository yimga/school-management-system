"""Migration Cloud lifecycle event emission (partner webhook bus).

The ONE place that publishes a bundle-lifecycle event to every ACTIVE webhook
subscription of the bundle's tenant. Emitting HERE — at the service layer —
rather than only inside the REST viewset is what lets UI-driven migrations (the
connector upload flow, the customer wizard) fire the same partner events an
API-driven migration does. Before this, only the REST advance/apply actions
emitted, and only ``bundle.advanced`` / ``bundle.applied`` / ``bundle.failed`` —
so a migration run from the wizard produced zero webhooks and ``bundle.reconciled``
was never emitted at all. See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (G-5) and
the partner catalog docs/MIGRATION_CLOUD_EVENT_CATALOG.md.

Best-effort: a webhook-subsystem hiccup NEVER breaks the primary
apply / reconcile / rollback path.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Canonical lifecycle event-type strings — single source of truth so producers
# and the partner catalog cannot drift.
EVENT_BUNDLE_ADVANCED = "bundle.advanced"
EVENT_BUNDLE_APPLIED = "bundle.applied"
EVENT_BUNDLE_FAILED = "bundle.failed"
EVENT_BUNDLE_RECONCILED = "bundle.reconciled"
EVENT_BUNDLE_ROLLED_BACK = "bundle.rolled_back"
EVENT_SHADOW_TRIPPED = "shadow.tripped"

LIFECYCLE_EVENT_TYPES = (
    EVENT_BUNDLE_ADVANCED,
    EVENT_BUNDLE_APPLIED,
    EVENT_BUNDLE_FAILED,
    EVENT_BUNDLE_RECONCILED,
    EVENT_BUNDLE_ROLLED_BACK,
    EVENT_SHADOW_TRIPPED,
)


def emit_bundle_lifecycle_event(
    bundle, event_type: str, payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort: enqueue webhook deliveries for a bundle-lifecycle event.

    Fires for EVERY active webhook subscription of the bundle's tenant, on both
    the API and UI code paths. Never raises — a webhook failure must not break
    the primary apply / reconcile / rollback.
    """
    try:
        # Local imports — avoid app-load cycles during Django startup.
        from apps.migration_cloud.api.webhook_dispatch import enqueue
        from apps.migration_cloud.models import MigrationCloudWebhookSubscription

        if not bundle or not getattr(bundle, "school_id", None):
            return
        # tenant-isolation-allow: webhook-lifecycle-enqueue-scoped-via-bundle-school-id
        subs = MigrationCloudWebhookSubscription.objects.filter(
            tenant_id=bundle.school_id, active=True,
        )
        body = dict(payload or {})
        body.setdefault("bundle_id", str(getattr(bundle, "pk", "")))
        body.setdefault("event", event_type)
        for sub in subs:
            enqueue(sub, event_type, body)
    except Exception:  # noqa: BLE001 — webhook emission is best-effort, never fatal
        logger.exception(
            "migration_cloud.lifecycle_events: emit failed bundle_id=%s event=%s",
            getattr(bundle, "pk", None), event_type,
        )
