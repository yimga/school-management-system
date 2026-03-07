"""
Compatibility facade for the deprecated siteconfig webhook runtime.

The canonical delivery stack now lives in apps.events.webhooks. Keep this import
surface only while older call sites are being removed.
"""

from apps.events.webhooks import (  # noqa: F401
    canonical_json_bytes,
    dispatch_due_webhooks,
    deliver_webhook_delivery,
    enqueue_webhook_event,
    replay_webhook_delivery,
    sign_payload,
)

__all__ = [
    "canonical_json_bytes",
    "dispatch_due_webhooks",
    "deliver_webhook_delivery",
    "enqueue_webhook_event",
    "replay_webhook_delivery",
    "sign_payload",
]
