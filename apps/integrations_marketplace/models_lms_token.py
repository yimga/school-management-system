"""v4.00.47 — LMS connector token storage (Wedge 2 — Canvas / Moodle / Google Classroom).

Stores per-(tenant, provider) OAuth2 access + refresh tokens for the
LMS adapter SOT shipped at v4.00.46 (``apps.api.lms_adapters``).

Tokens are Fernet-encrypted via the shim at
``apps.accounts.legacy_hashes.encryption.EncryptedCharField`` so the
DB column never holds plaintext bearer material. The same MultiFernet
rotation behaviour applies (latest key writes; any key reads).
"""
from __future__ import annotations

from django.db import models

from apps.accounts.legacy_hashes.encryption import EncryptedCharField


class LMSConnectorToken(models.Model):
    """OAuth2 bearer + refresh tokens for an LMS connector.

    One row per (school, provider) pair. ``base_url`` is the customer's
    LMS root (e.g. ``https://canvas.school.edu``); Google Classroom may
    leave it empty because the API lives at ``classroom.googleapis.com``.
    """

    class Provider(models.TextChoices):
        CANVAS = "canvas", "Canvas LMS"
        MOODLE = "moodle", "Moodle"
        GOOGLE_CLASSROOM = "google_classroom", "Google Classroom"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lms_connector_tokens",
    )
    provider = models.CharField(max_length=24, choices=Provider.choices, db_index=True)
    base_url = models.CharField(max_length=255, blank=True, default="")
    access_token = EncryptedCharField(max_length=2048, blank=True, default="")
    refresh_token = EncryptedCharField(max_length=2048, blank=True, default="")
    scope = models.CharField(max_length=512, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_marketplace"
        unique_together = ("school", "provider")
        ordering = ("school_id", "provider")
        verbose_name = "LMS connector token"
        verbose_name_plural = "LMS connector tokens"

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({self.school_id})"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def masked_token(self) -> str:
        tok = self.access_token or ""
        if not tok:
            return ""
        if len(tok) <= 8:
            return "***"
        return f"{tok[:4]}...{tok[-4:]}"
