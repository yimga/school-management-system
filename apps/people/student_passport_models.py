"""
Student passport (portable identity) and transcript vault (North Star SLICE 13).

Cross-tenant access requires explicit membership + consent on the vault/membership row.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StudentPassportMembership(models.Model):
    """Links a passport to an enrollment (student profile) within one tenant."""

    class ConsentStatus(models.TextChoices):
        PRIVATE = "private", _("Private")
        SHARED_WITH_SCHOOL = "shared_with_school", _("Shared with school")
        REVOKED = "revoked", _("Revoked")

    passport = models.ForeignKey(
        "people.StudentPassport",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_passport_memberships",
    )
    student_profile = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="passport_memberships",
    )
    role = models.CharField(max_length=40, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    consent_status = models.CharField(
        max_length=32,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PRIVATE,
        db_index=True,
    )

    class Meta:
        unique_together = ("passport", "school", "student_profile")
        indexes = [
            models.Index(fields=["school", "student_profile"]),
            models.Index(fields=["passport", "school"]),
        ]

    def __str__(self) -> str:
        return f"{self.passport_id} @ {self.school_id}"


class TranscriptVaultItem(models.Model):
    """Stored transcript/report artifact reference + verification hash (no fake credential UX)."""

    class AccessStatus(models.TextChoices):
        PRIVATE = "private", _("Private")
        SHARED_WITH_SCHOOL = "shared_with_school", _("Shared with school")
        REVOKED = "revoked", _("Revoked")

    passport = models.ForeignKey(
        "people.StudentPassport",
        on_delete=models.CASCADE,
        related_name="vault_items",
    )
    issuing_school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="issued_transcript_vault_items",
    )
    student_profile = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="transcript_vault_items",
    )
    artifact_type = models.CharField(max_length=64)
    artifact_ref = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("Storage path, external document id, or opaque reference."),
    )
    verification_hash = models.CharField(max_length=128, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    access_status = models.CharField(
        max_length=32,
        choices=AccessStatus.choices,
        default=AccessStatus.PRIVATE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        indexes = [
            models.Index(fields=["passport", "access_status"]),
            models.Index(fields=["student_profile", "issuing_school"]),
        ]

    def __str__(self) -> str:
        return f"{self.artifact_type} ({self.pk})"
