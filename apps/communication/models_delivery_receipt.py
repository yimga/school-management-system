"""SMS / WhatsApp / push delivery receipts (audit residual closeout).

Email already has per-send forensics in
:class:`apps.schoolops.models_email_delivery.EmailDeliveryEvent`; the other
channels had none — once an SMS or WhatsApp message left the provider adapter
we never learned whether it was delivered, failed, or undelivered. Providers
report this asynchronously via status callbacks (Twilio ``MessageStatus``) or
the webhook ``statuses`` array (Meta WhatsApp Cloud API).

:class:`MessageDeliveryReceipt` is the unified landing table for those signals,
keyed by the provider's own message id so a later status update upserts the same
row (``queued`` → ``sent`` → ``delivered``).

PII contract
------------
We store ONLY ``recipient_hash`` = sha256(recipient.lower())[:12] — never the
raw phone number / token. The provider message id is an opaque vendor handle,
not PII.
"""
from __future__ import annotations

import uuid

from django.db import models


class DeliveryChannel(models.TextChoices):
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"
    PUSH = "push", "Push notification"


class MessageDeliveryReceipt(models.Model):
    """Latest known delivery status for one outbound message on one channel.

    Upserted by the Twilio status-callback webhook
    (:mod:`apps.communication.views_sms_inbound_webhook`) and the WhatsApp
    webhook ``statuses`` handler. ``status`` is the verbatim provider label,
    lower-cased; ``terminal`` marks delivered/failed/undelivered so dashboards
    can filter the in-flight set cheaply.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.CharField(
        max_length=12,
        choices=DeliveryChannel.choices,
        db_index=True,
    )
    provider = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Provider key: 'twilio' | 'africastalking' | 'meta_whatsapp'.",
    )
    provider_message_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="The provider's own message id (Twilio SID / Meta wamid).",
    )
    recipient_hash = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="sha256(recipient.lower())[:12] — never the raw phone/token.",
    )
    status = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Verbatim provider status, lower-cased (queued/sent/delivered/…).",
    )
    error_code = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Provider error code on failure/undelivered (e.g. Twilio 30007).",
    )
    terminal = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True once the status is delivered/failed/undelivered/read.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_delivery_receipts",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "communication"
        db_table = "communication_message_delivery_receipt"
        ordering = ["-updated_at"]
        verbose_name = "Message delivery receipt"
        verbose_name_plural = "Message delivery receipts"
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "provider_message_id"],
                name="comm_delivery_receipt_channel_msgid_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["channel", "status"]),
            models.Index(fields=["terminal", "updated_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"MessageDeliveryReceipt[{self.channel}:{self.status}] "
            f"msg_id={self.provider_message_id}"
        )


__all__ = ["MessageDeliveryReceipt", "DeliveryChannel"]
