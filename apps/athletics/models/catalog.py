"""Sport catalog, seasons, and kit-fee catalog."""

from __future__ import annotations

from django.db import models

from apps.athletics.constants import DEFAULT_SQUAD_SIZE


class SportCategory(models.TextChoices):
    TEAM = "team", "Team sport"
    INDIVIDUAL = "individual", "Individual sport"


class GenderCategory(models.TextChoices):
    BOYS = "boys", "Boys"
    GIRLS = "girls", "Girls"
    MIXED = "mixed", "Mixed"


class Sport(models.Model):
    """A per-tenant sport the school offers (seeded, operator-extendable)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_sports"
    )
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40)
    category = models.CharField(
        max_length=16, choices=SportCategory.choices, default=SportCategory.TEAM
    )
    gender_category = models.CharField(
        max_length=8, choices=GenderCategory.choices, default=GenderCategory.MIXED
    )
    default_squad_size = models.PositiveSmallIntegerField(default=DEFAULT_SQUAD_SIZE)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["name"]
        unique_together = [("school", "code")]
        indexes = [models.Index(fields=["school", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"


class Season(models.Model):
    """A competitive season for a sport within an academic year."""

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_seasons"
    )
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="seasons")
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_seasons",
    )
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PLANNING
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-start_date"]
        unique_together = [("school", "sport", "academic_year", "name")]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.sport_id})"


class TeamKitFee(models.Model):
    """Kit/participation fee catalog a team's memberships invoice against."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_kit_fees"
    )
    team = models.ForeignKey(
        "athletics.Team", on_delete=models.CASCADE, related_name="kit_fees"
    )
    label = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["label"]
        unique_together = [("team", "label")]
        indexes = [models.Index(fields=["school", "is_active"])]

    def __str__(self) -> str:
        return f"{self.label}: {self.amount}"


__all__ = ["Sport", "Season", "TeamKitFee", "SportCategory", "GenderCategory"]
