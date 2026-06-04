"""Email dead-letter queue (audit residual closeout).

When a transactional send permanently fails for a RETRY-eligible reason
(transient SMTP / connection exhaustion — NOT a hard bounce, suppression, or
header-injection) and the operator has opted in via
``settings.SCHOOLOPS_EMAIL_DLQ_ENABLED``, the full resend payload is parked in
:class:`EmailDeadLetter` so it can be redriven once the relay recovers
(``python manage.py redrive_email_dead_letters``).

PII contract
------------
The DLQ is the ONE place the platform must hold a renderable copy of a message
(subject + body + recipients) — a redrive cannot reconstruct the mail
otherwise. We therefore Fernet-encrypt the entire payload at rest
(:attr:`payload_encrypted`) using the same key chain as the stored SMTP
password, and only decrypt it transiently inside the redrive worker. The
hashed recipient (:attr:`to_hash`) and the 64-char redacted subject prefix are
the only plaintext, mirroring :class:`EmailDeliveryEvent`. Because the encrypted
blob is the only PII at rest, the DLQ is default-OFF: no bodies are stored
unless an operator turns the queue on.

Unlike :class:`EmailDeliveryEvent` this model is NOT append-only — the redrive
worker flips ``status`` and bumps ``redrive_count`` as it works the queue.
"""
from __future__ import annotations

import uuid

from django.db import models


class DeadLetterStatus(models.TextChoices):
    PENDING = "pending", "Pending redrive"
    REDRIVEN = "redriven", "Redriven (delivered)"
    EXHAUSTED = "exhausted", "Redrive attempts exhausted"
    ABANDONED = "abandoned", "Abandoned by operator"


class EmailDeadLetter(models.Model):
    """A permanently-failed transactional send, parked for later redrive.

    Written by :func:`apps.schoolops.email_delivery._maybe_enqueue_dead_letter`
    and worked by :func:`apps.schoolops.email_delivery.redrive_dead_letters`.
    Platform-level (NOT tenant-scoped): the operator dashboard wants one
    cross-tenant view of stuck mail.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUIDv4 primary key.",
    )
    to_hash = models.CharField(
        max_length=12,
        db_index=True,
        help_text="sha256(recipient_email.lower())[:12] — never the raw address.",
    )
    subject_prefix = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Redacted 64-char subject snapshot (display only).",
    )
    priority = models.CharField(
        max_length=24,
        default="transactional",
        help_text="Send priority class carried over from the original send.",
    )
    payload_encrypted = models.TextField(
        help_text=(
            "Fernet-encrypted JSON of the full resend payload (subject, body, "
            "html_body, recipients, reply_to, from_email, headers, school_id). "
            "Decrypted ONLY transiently inside the redrive worker."
        ),
    )
    error_kind = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Coarse error_kind from the failing send that parked this row.",
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="SMTP attempts the original send made before being parked.",
    )
    status = models.CharField(
        max_length=16,
        choices=DeadLetterStatus.choices,
        default=DeadLetterStatus.PENDING,
        db_index=True,
        help_text="Lifecycle: pending → redriven | exhausted | abandoned.",
    )
    redrive_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of redrive attempts made by the worker so far.",
    )
    last_error_kind = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="error_kind from the most recent redrive attempt.",
    )
    delivery_event_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="UUID of the EmailDeliveryEvent row for the original failure.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    redriven_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the row reached a terminal redriven/exhausted state.",
    )

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_email_dead_letter"
        ordering = ["created_at"]
        verbose_name = "Email dead letter"
        verbose_name_plural = "Email dead letters"
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"EmailDeadLetter[{self.status}] to_hash={self.to_hash} "
            f"redrives={self.redrive_count}"
        )


__all__ = ["EmailDeadLetter", "DeadLetterStatus"]
