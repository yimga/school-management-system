"""Cross-channel consent event log (audit residual closeout).

A single append-only audit trail for opt-in / opt-out events across every
messaging channel (email, SMS, WhatsApp, push). It is BOTH the compliance
record (who opted out of what, when, and via which surface — CAN-SPAM / CASL /
GDPR / TCPA evidence) AND the source-of-truth the SMS/WhatsApp send paths
consult before sending: :func:`apps.communication.consent.is_channel_suppressed`
reads the latest event per ``(channel, identifier)`` and treats a trailing
``withdrawn`` as a block.

Why a separate log from the email :class:`SuppressedRecipient`
-------------------------------------------------------------
Email already has a bounce/complaint suppression list keyed by reason; this log
captures the *consent decision* (a parent texting STOP, a guardian toggling a
preference) which is a distinct legal concept and spans channels email never
had to model (SMS/WhatsApp). The email unsubscribe flow writes to BOTH (the
suppression list for the send hot-path, the consent log for the audit trail).

PII contract
------------
We store ONLY ``identifier_hash`` = sha256(identifier.lower())[:12] — never the
raw email address or phone number. Lookups are hashed-key, so the log is
forensically useful without holding PII.
"""
from __future__ import annotations

import uuid

from django.db import models


class ConsentChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"
    PUSH = "push", "Push notification"


class ConsentAction(models.TextChoices):
    GRANTED = "granted", "Consent granted / opted in"
    WITHDRAWN = "withdrawn", "Consent withdrawn / opted out"
    HELP_REQUESTED = "help_requested", "Help requested"


class ConsentEventReadOnlyError(Exception):
    """Raised when code tries to mutate or delete a consent event row."""


class ConsentEvent(models.Model):
    """Append-only record of one consent decision on one channel.

    Written by the SMS inbound webhook (STOP/START/HELP), the newsletter
    unsubscribe flow, and any preference-centre toggle. Read by
    :func:`apps.communication.consent.is_channel_suppressed`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.CharField(
        max_length=12,
        choices=ConsentChannel.choices,
        db_index=True,
        help_text="Messaging channel the decision applies to.",
    )
    identifier_hash = models.CharField(
        max_length=12,
        db_index=True,
        help_text="sha256(identifier.lower())[:12] — never the raw email/phone.",
    )
    action = models.CharField(
        max_length=16,
        choices=ConsentAction.choices,
        help_text="granted | withdrawn | help_requested.",
    )
    reason = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Coarse machine reason, e.g. the keyword ('stop'/'start').",
    )
    source = models.CharField(
        max_length=48,
        blank=True,
        default="",
        help_text="Origin surface: 'sms_webhook' | 'newsletter' | 'preference_centre'.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_events",
        help_text="Tenant context when known (platform-level events leave null).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "communication"
        db_table = "communication_consent_event"
        ordering = ["-created_at"]
        verbose_name = "Consent event"
        verbose_name_plural = "Consent events"
        indexes = [
            models.Index(fields=["channel", "identifier_hash", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"ConsentEvent[{self.channel}:{self.action}] "
            f"id_hash={self.identifier_hash}"
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ConsentEventReadOnlyError(
                "ConsentEvent rows are append-only; update refused."
            )
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ConsentEventReadOnlyError(
            "ConsentEvent rows are append-only; delete refused."
        )


__all__ = [
    "ConsentEvent",
    "ConsentChannel",
    "ConsentAction",
    "ConsentEventReadOnlyError",
]
