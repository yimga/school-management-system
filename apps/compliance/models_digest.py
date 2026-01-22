"""
Alert digest model for batching non-critical notifications.
"""
from django.db import models
from django.utils import timezone
from django.conf import settings


class AlertDigest(models.Model):
    """
    Pending alerts to be sent in batch (hourly/daily digest).
    """

    class AlertType(models.TextChoices):
        AUDIT = "AUDIT", "Audit Event"
        THREAT = "THREAT", "Threat Finding"
        ACCESS = "ACCESS", "Access Control"
        SYSTEM = "SYSTEM", "System Event"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)

    # Status
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    source = models.CharField(max_length=100, blank=True, help_text="Source module or function")
    related_model = models.CharField(max_length=100, blank=True)
    related_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_sent", "created_at"]),
            models.Index(fields=["alert_type", "severity"]),
        ]

    def __str__(self):
        status = "Sent" if self.is_sent else "Pending"
        return f"[{status}] {self.alert_type} - {self.subject}"

    def mark_sent(self):
        """Mark alert as sent."""
        self.is_sent = True
        self.sent_at = timezone.now()
        self.save(update_fields=["is_sent", "sent_at"])
