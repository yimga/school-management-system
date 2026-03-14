"""
Event Outbox: transactional outbox for domain events (RunMyCampus blueprint).
Emit from service layer only; consumer processes outbox for webhooks, notifications, automation.
"""
import uuid
from django.db import models


class DomainEvent(models.Model):
    """
    Outbox table: one row per emitted domain event.
    Consumer (Celery task or cron) processes pending rows and dispatches to webhooks/handlers.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=128, db_index=True)
    schema_version = models.CharField(
        max_length=32,
        default="1.0",
        help_text="Event payload schema version for consumers (26.2).",
    )
    payload = models.JSONField(default=dict, help_text="Event payload (e.g. entity id, type, changes)")
    # Tenant context: for RLS use school_id; for schema-per-tenant use schema_name (or both for routing)
    school_id = models.UUIDField(null=True, blank=True, db_index=True)
    schema_name = models.CharField(max_length=63, null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    retry_count = models.PositiveIntegerField(default=0)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "events"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="events_status_created_idx"),
        ]
        verbose_name = "Domain Event"
        verbose_name_plural = "Domain Events"

    def __str__(self):
        return f"{self.event_type} ({self.status})"


class WebhookSubscription(models.Model):
    """
    Tenant- or platform-managed webhook endpoint: receive domain events (RunMyCampus blueprint).
    Retries and signing via WebhookDelivery.
    """

    school_id = models.UUIDField(null=True, blank=True, db_index=True)
    url = models.URLField(max_length=2048)
    event_types = models.JSONField(
        default=list,
        help_text="List of event_type strings (e.g. ['student.enrolled', 'grade.published']). Empty = all.",
    )
    secret = models.CharField(max_length=255, blank=True, help_text="Used for HMAC signature of payload")
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "events"
        verbose_name = "Webhook Subscription"
        verbose_name_plural = "Webhook Subscriptions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.url[:50]}… ({self.school_id or 'platform'})"


class WebhookDelivery(models.Model):
    """
    One delivery attempt for a domain event to a webhook subscription.
    Retries, response code, and signing (idempotency key in header).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    domain_event = models.ForeignKey(
        DomainEvent,
        on_delete=models.CASCADE,
        related_name="webhook_deliveries",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    http_status = models.PositiveIntegerField(null=True, blank=True)
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Next time this delivery is eligible for processing.",
    )
    attempted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=4)
    error_message = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "events"
        verbose_name = "Webhook Delivery"
        verbose_name_plural = "Webhook Deliveries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="events_wh_status_created"),
            models.Index(fields=["status", "scheduled_for"], name="events_wh_status_sched"),
        ]

    def __str__(self):
        return f"{self.subscription_id} → {self.domain_event_id} ({self.status})"
