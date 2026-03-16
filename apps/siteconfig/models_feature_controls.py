from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class FeatureToggleDefinition(models.Model):
    """
    Registry of configurable toggles.
    Supports global defaults plus optional per-school overrides.
    """

    class Scope(models.TextChoices):
        GLOBAL = "global", "Global only"
        SCHOOL = "school", "School override allowed"

    key = models.SlugField(max_length=120, unique=True)
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.SCHOOL)
    owner = models.CharField(
        max_length=120,
        blank=True,
        help_text="Team or person responsible for this toggle (e.g. platform, product).",
    )
    source = models.CharField(
        max_length=80,
        blank=True,
        help_text="Origin of the flag (e.g. capability_registry, legacy_backend_flags).",
    )
    default_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "label", "key"]

    def __str__(self):
        return self.label or self.key


class FeatureToggleState(models.Model):
    """
    Effective toggle values.
    - school=None => global override
    - school=<id> => tenant override
    """

    definition = models.ForeignKey(
        FeatureToggleDefinition,
        on_delete=models.CASCADE,
        related_name="states",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_toggle_states",
        null=True,
        blank=True,
    )
    is_enabled = models.BooleanField(default=False)
    value = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, this override is ignored after this time (Phase 10 — 10.2 capability expiry).",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_feature_toggle_states",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "school"],
                name="siteconfig_toggle_state_unique_definition_school",
            )
        ]
        ordering = ["definition__key", "school_id"]

    def __str__(self):
        scope = self.school.slug if self.school_id else "global"
        return f"{self.definition.key} ({scope})"


class TourStep(models.Model):
    """In-app onboarding tour step; track which users have seen which step."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tour_steps",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=80, db_index=True, help_text="e.g. dashboard_welcome, grades_first_time")
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        unique_together = [("school", "code")]

    def __str__(self):
        return f"{self.code}: {self.title or self.code}"


class FeatureUsageEvent(models.Model):
    """Feature-usage analytics: track_event(feature_code, school, user)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_usage_events",
        null=True,
        blank=True,
    )
    feature_code = models.CharField(max_length=80, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_usage_events",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "feature_code", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.feature_code} @ {self.created_at}"


class GlobalSupportTicket(models.Model):
    """
    Central support ticket from any tenant; stored in public/shared schema.
    Super-admin command center can filter by tenant, priority, region (metadata.country_code).
    Auto-prioritize by plan (e.g. Powerhouse).
    """

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        WAITING = "WAITING", "Waiting"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="global_support_tickets",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="global_support_tickets_submitted",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        help_text="Super-admin or support agent assigned to this ticket.",
    )
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="country_code, plan_slug, etc. for regional routing and filters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_response_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the first agent response was recorded; used for SLA response breach.",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["school"]),
            models.Index(fields=["-created_at"]),
        ]
        verbose_name = "Global support ticket"
        verbose_name_plural = "Global support tickets"

    def __str__(self):
        return f"{self.school.name}: {self.subject} ({self.status})"
