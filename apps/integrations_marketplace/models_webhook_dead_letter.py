"""v4.00.79 — WebhookDeadLetter persistence model.

Companion to ``webhook_retry_fsm.py``: when a webhook delivery exhausts
the canonical retry budget (1m / 5m / 30m / 2h / 12h / 24h, then
``is_exhausted`` returns True), the dispatch worker parks the payload
here for operator-driven replay or auto-expiry.

Storage shape is deliberately opaque: ``payload_b64`` is the
base64-encoded original payload bytes — we never try to JSON-decode it
at park time, because the body could be malformed (that may be WHY the
delivery failed). The replay endpoint (Wave 12) decodes on read.

PII-safe by design: only ``provider`` / ``event_type`` /
``last_error_reason`` are queryable. The payload sits behind b64 so it
won't get accidentally indexed or surfaced by a list-view template.
"""
from __future__ import annotations

from django.db import models


_STATUS_CHOICES = [
    ("pending", "pending"),
    ("replayed", "replayed"),
    ("expired", "expired"),
    ("discarded", "discarded"),
]


class WebhookDeadLetter(models.Model):
    """One row per webhook delivery that exhausted its retry budget."""

    provider = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=128, db_index=True)
    payload_b64 = models.TextField()
    attempt_count = models.PositiveIntegerField(default=0)
    last_error_reason = models.CharField(max_length=256, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    tenant_schema = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Cross-tenant safety marker — replay endpoint refuses cross-schema replay.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        app_label = "integrations_marketplace"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["provider", "status", "created_at"],
                name="dlq_psc_idx",
            ),
            models.Index(
                fields=["status", "expires_at"],
                name="dlq_se_idx",
            ),
        ]
        verbose_name = "Webhook Dead Letter"

    def __str__(self) -> str:
        return (
            f"WebhookDeadLetter(id={self.pk}, provider={self.provider}, "
            f"status={self.status})"
        )
