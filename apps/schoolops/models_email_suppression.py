"""Email suppression list — bounce/complaint/unsubscribe enforcement.

Audit finding H3 (2026-06-03): the platform recorded hard bounces on
``EmailDeliveryEvent.bounced`` but nothing consulted that history before the
*next* send, so a hard-bounced / complained address was re-mailed on every
subsequent trigger — directly damaging sender reputation (Gmail/Yahoo bulk-
sender rules require a spam-complaint rate below 0.3%).

``SuppressedRecipient`` is the SOT the send hot-path checks *before* every
send. Rows are written by:

  * the inbound bounce/complaint webhook (:mod:`apps.schoolops.views_email_webhook`)
    on a hard bounce or spam complaint;
  * the send hot-path itself when an SMTP send permanently bounces;
  * the newsletter unsubscribe flow (marketing opt-out).

PII contract
------------
Mirrors :class:`EmailDeliveryEvent`: we store ONLY ``to_hash`` =
sha256(recipient.lower())[:12], never the raw address. Suppression is a
hashed-key lookup, so the list is forensically useful without holding PII.

Reversibility
-------------
Suppression is a soft state — ``active=False`` lifts it (e.g. an operator
clears a transient block, or a user re-subscribes). The row is retained for
audit; we never delete suppression history.
"""
from __future__ import annotations

from django.db import models


class SuppressionReason(models.TextChoices):
    HARD_BOUNCE = "hard_bounce", "Hard bounce"
    COMPLAINT = "complaint", "Spam complaint"
    UNSUBSCRIBE = "unsubscribe", "Marketing unsubscribe"
    MANUAL = "manual", "Manual operator block"


class SuppressedRecipient(models.Model):
    """A recipient address (hashed) the platform must not send to.

    Looked up by :func:`apps.schoolops.email_delivery.is_recipient_suppressed`
    at the top of every send. Platform-level (NOT tenant-scoped) — a hard
    bounce is a property of the address, not of a tenant.
    """

    to_hash = models.CharField(
        max_length=12,
        unique=True,
        db_index=True,
        help_text="sha256(recipient_email.lower())[:12] — never the raw address.",
    )
    reason = models.CharField(
        max_length=24,
        choices=SuppressionReason.choices,
        default=SuppressionReason.HARD_BOUNCE,
        help_text="Why this recipient is suppressed.",
    )
    source = models.CharField(
        max_length=48,
        blank=True,
        default="",
        help_text="Coarse origin: 'webhook' | 'send_time' | 'unsubscribe' | 'operator'.",
    )
    detail = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Optional non-PII detail (e.g. provider bounce label, vendor code).",
    )
    active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True = suppress sends. False = lifted (re-subscribe / operator clear).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_email_suppressed_recipient"
        ordering = ["-updated_at"]
        verbose_name = "Suppressed email recipient"
        verbose_name_plural = "Suppressed email recipients"
        indexes = [
            models.Index(fields=["active", "reason"]),
        ]

    def __str__(self) -> str:
        state = "active" if self.active else "lifted"
        return f"SuppressedRecipient[{state}] to_hash={self.to_hash} reason={self.reason}"


__all__ = ["SuppressedRecipient", "SuppressionReason"]
