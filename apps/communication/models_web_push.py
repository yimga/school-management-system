"""Browser Web Push subscription storage (Push API + VAPID)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class WebPushSubscription(models.Model):
    """One row per browser push endpoint for an authenticated user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="web_push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]
        verbose_name = "Web push subscription"
        verbose_name_plural = "Web push subscriptions"

    def __str__(self) -> str:
        return f"web-push:{getattr(self.user, 'pk', '?')}"

    def subscription_info(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }
