from __future__ import annotations

from django.conf import settings
from django.db import models
import uuid


class PortalFeatureItem(models.Model):
    class Feature(models.TextChoices):
        MESSAGING = "messaging", "Messaging"
        FORUMS = "forums", "Forums"
        VIDEO = "video", "Video"
        DOCUMENTS = "documents", "Documents"
        SYLLABUS = "syllabus", "Syllabus"

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


class PendingGuardianInvite(models.Model):
    """
    A lightweight invite that lets staff issue a claim token to a parent/guardian.
    The parent claims it from the portal and we create the StudentGuardian link.
    """

    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        GUARDIAN = "GUARDIAN", "Guardian"
        OTHER = "OTHER", "Other"

    class PreferredContact(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        PHONE = "PHONE", "Phone Call"

    token = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey("people.StudentProfile", on_delete=models.CASCADE, related_name="pending_invites")
    invited_email = models.EmailField(blank=True)
    invited_phone = models.CharField(max_length=50, blank=True)
    relationship = models.CharField(
        max_length=20, choices=Relationship.choices, default=Relationship.GUARDIAN
    )
    preferred_contact = models.CharField(
        max_length=20, choices=PreferredContact.choices, default=PreferredContact.EMAIL
    )
    referral_code = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="guardian_invites"
    )
    guardian_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="claimed_invites"
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite {self.student} -> {self.invited_email or self.invited_phone or self.token}"

    @property
    def is_claimed(self) -> bool:
        return bool(self.claimed_at and self.guardian_user)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)
