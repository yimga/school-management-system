"""v3.57.x Wave 8 Agent C — Append-only email delivery event log.

``EmailDeliveryEvent`` is the per-send platform-level audit row written
by :mod:`apps.schoolops.email_delivery`. It powers the operator email
health dashboard and lets reliability sweeps surface SMTP regressions
without paging through SMTP server logs.

PII contract — what we DO NOT persist
-------------------------------------

  * Recipient email address. Only ``to_hash`` = sha256(to)[:12].
  * From-email address (operator-config concern, not per-send concern).
  * Subject line beyond a 64-char ``subject_prefix`` snapshot. The
    sender truncates the snapshot before calling ``record()``, so the
    DB row never holds a long subject either.
  * Message body. Never. Anywhere.

Append-only enforcement
-----------------------

This model mirrors the ``MigrationCloudAuditEvent`` pattern: ``save()``
on an existing row raises :class:`EmailDeliveryEventReadOnlyError`,
``delete()`` raises unconditionally. The intent is forensic — a
failing send tomorrow must be auditable as it happened, not as
something rewritten by a later codepath.

Tenant scoping
--------------

The email delivery log is platform-level (NOT tenant-scoped). The
operator dashboard and reliability sweeps both want a cross-tenant
view. Every ``EmailDeliveryEvent.objects.filter(...)`` callsite is
therefore marked
``# tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope``.
"""
from __future__ import annotations

import uuid

from django.db import models


class EmailDeliveryEventReadOnlyError(Exception):
    """Raised when code tries to mutate or delete an email-delivery row."""


class EmailDeliveryEvent(models.Model):
    """Append-only forensic log of every transactional / bulk email send.

    Written by :func:`apps.schoolops.email_delivery.send_transactional`
    and :func:`apps.schoolops.email_delivery.send_bulk`. Read by the
    operator email-health dashboard.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=(
            "UUIDv4 primary key. Random so event IDs don't leak ordering "
            "or per-tenant volume."
        ),
    )
    to_hash = models.CharField(
        max_length=12,
        db_index=True,
        help_text=(
            "First 12 hex chars of sha256(recipient_email). Used to "
            "correlate retries to a single recipient WITHOUT persisting "
            "the raw address."
        ),
    )
    subject_prefix = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "First 64 chars of the subject line, redacted by the caller. "
            "Stored verbatim — the caller's responsibility to strip "
            "anything PII-shaped before record()."
        ),
    )
    priority = models.CharField(
        max_length=24,
        default="transactional",
        help_text=(
            "Send priority class: 'transactional' (verification, password "
            "reset, low-balance) or 'bulk' (digest, newsletter)."
        ),
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Number of SMTP send attempts made for this event (1..N where "
            "N is the retry backoff length)."
        ),
    )
    ok = models.BooleanField(
        default=False,
        help_text=(
            "True iff the final SMTP attempt returned without raising. "
            "False if every attempt raised; see ``error_kind`` for the "
            "kind of failure observed on the last attempt."
        ),
    )
    error_kind = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "One of 'smtp_exception' | 'os_error' | 'connection_error' | "
            "'value_error' | '' (success). Coarse-grained on purpose — the "
            "dashboard shows kinds, not stack traces."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Wall-clock time of the LAST attempt (success or failure).",
    )

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_email_delivery_event"
        ordering = ["-created_at"]
        verbose_name = "Email delivery event"
        verbose_name_plural = "Email delivery events"
        indexes = [
            models.Index(fields=["to_hash", "created_at"]),
            models.Index(fields=["ok", "created_at"]),
        ]

    def __str__(self) -> str:
        status = "ok" if self.ok else "fail"
        return (
            f"EmailDeliveryEvent[{status}] to_hash={self.to_hash} "
            f"priority={self.priority} attempts={self.attempts}"
        )

    # ------------------------------------------------------------------
    # Append-only enforcement (mirrors MigrationCloudAuditEvent pattern).
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if self.pk is not None:
            existing = (
                type(self).objects  # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
                .filter(pk=self.pk)
                .only("pk")
                .first()
            )
            if existing is not None:
                raise EmailDeliveryEventReadOnlyError(
                    "EmailDeliveryEvent rows are append-only; update refused."
                )
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise EmailDeliveryEventReadOnlyError(
            "EmailDeliveryEvent rows are append-only; delete refused."
        )


__all__ = [
    "EmailDeliveryEvent",
    "EmailDeliveryEventReadOnlyError",
]
