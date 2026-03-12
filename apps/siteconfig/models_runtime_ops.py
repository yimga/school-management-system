from __future__ import annotations

from django.conf import settings
from django.db import models


class BreakGlassOverride(models.Model):
    """
    World Engine: break-glass protocol — emergency override (e.g. unlock, bypass) with audit.
    Scope = e.g. 'lockdown_unlock', 'impersonation_bypass'; actor = who invoked; reason required.
    """

    scope = models.CharField(max_length=80, db_index=True)
    target_id = models.CharField(max_length=255, blank=True, help_text="e.g. user_id, school_id.")
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scope", "target_id"])]

    def __str__(self):
        return f"{self.scope} by {self.actor_id} @ {self.created_at}"


class BroadcastCampaign(models.Model):
    """
    World Engine: Emergency Broadcast — message to 5k+ devices; WebSocket/Redis Pub/Sub; optional Slide to Confirm.
    Celery task fans out in chunks; delivery tracked per recipient.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUEUED = "QUEUED", "Queued"
        SENDING = "SENDING", "Sending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="broadcast_campaigns",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    slide_confirm_required = models.BooleanField(default=True, help_text="Recipient must slide-to-confirm.")
    target_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.status})"
