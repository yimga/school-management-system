"""Fixtures (matches), results, and away-fixture travel."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Fixture(models.Model):
    """A scheduled match a team plays."""

    class FixtureType(models.TextChoices):
        HOME = "home", "Home"
        AWAY = "away", "Away"
        NEUTRAL = "neutral", "Neutral"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CONFIRMED = "confirmed", "Confirmed"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        POSTPONED = "postponed", "Postponed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_fixtures"
    )
    team = models.ForeignKey(
        "athletics.Team", on_delete=models.CASCADE, related_name="fixtures"
    )
    season = models.ForeignKey(
        "athletics.Season", on_delete=models.PROTECT, related_name="fixtures"
    )
    opponent_name = models.CharField(max_length=200)
    opponent_team = models.ForeignKey(
        "athletics.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fixtures_as_opponent",
    )
    fixture_type = models.CharField(
        max_length=8, choices=FixtureType.choices, default=FixtureType.HOME
    )
    venue = models.ForeignKey(
        "school_events.EventVenue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_fixtures",
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SCHEDULED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["scheduled_start"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["team", "scheduled_start"]),
        ]

    def __str__(self) -> str:
        return f"{self.team_id} vs {self.opponent_name} @ {self.scheduled_start:%Y-%m-%d}"


class FixtureResult(models.Model):
    """The recorded score/outcome of a fixture."""

    class Outcome(models.TextChoices):
        WIN = "win", "Win"
        LOSS = "loss", "Loss"
        DRAW = "draw", "Draw"
        VOID = "void", "Void"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_fixture_results",
    )
    fixture = models.OneToOneField(
        "athletics.Fixture", on_delete=models.CASCADE, related_name="result"
    )
    home_score = models.PositiveSmallIntegerField(default=0)
    away_score = models.PositiveSmallIntegerField(default=0)
    outcome = models.CharField(
        max_length=8, choices=Outcome.choices, default=Outcome.DRAW
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_results_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    is_final = models.BooleanField(default=True)

    class Meta:
        app_label = "athletics"
        constraints = [
            models.UniqueConstraint(fields=["fixture"], name="uniq_result_per_fixture")
        ]

    def __str__(self) -> str:
        return f"result {self.fixture_id}: {self.home_score}-{self.away_score}"


class FixtureTravel(models.Model):
    """Links an away fixture to a transport route (schoolops.Route)."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_fixture_travel",
    )
    fixture = models.OneToOneField(
        "athletics.Fixture", on_delete=models.CASCADE, related_name="travel"
    )
    route = models.ForeignKey(
        "schoolops.Route",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athletics_fixture_travel",
    )
    departure_time = models.DateTimeField(null=True, blank=True)
    return_time = models.DateTimeField(null=True, blank=True)
    pickup_point = models.CharField(max_length=128, blank=True)
    dropoff_point = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PLANNED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"travel {self.fixture_id} ({self.status})"


__all__ = ["Fixture", "FixtureResult", "FixtureTravel"]
