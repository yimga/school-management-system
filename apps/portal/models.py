from __future__ import annotations

from django.conf import settings
from django.db import models


class PortalFeatureItem(models.Model):
    class Feature(models.TextChoices):
        MESSAGING = "messaging", "Messaging"
        FORUMS = "forums", "Forums"
        VIDEO = "video", "Video"
        DOCUMENTS = "documents", "Documents"

    feature = models.CharField(max_length=20, choices=Feature.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portal_feature_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Portal Feature Item"
        verbose_name_plural = "Portal Feature Items"

    def __str__(self) -> str:
        return f"{self.get_feature_display()}: {self.title}"
