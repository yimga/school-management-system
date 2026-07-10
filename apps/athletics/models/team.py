"""Teams/squads and coach assignments."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.athletics.constants import DEFAULT_ROSTER_CAP
from apps.athletics.models.catalog import GenderCategory


class Team(models.Model):
    """A squad that plays fixtures within a season."""

    class Status(models.TextChoices):
        FORMING = "forming", "Forming"
        ACTIVE = "active", "Active"
        DISBANDED = "disbanded", "Disbanded"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="athletics_teams"
    )
    sport = models.ForeignKey(
        "athletics.Sport", on_delete=models.PROTECT, related_name="teams"
    )
    season = models.ForeignKey(
        "athletics.Season", on_delete=models.CASCADE, related_name="teams"
    )
    name = models.CharField(max_length=120)
    level = models.CharField(max_length=48, blank=True)
    gender = models.CharField(
        max_length=8, choices=GenderCategory.choices, default=GenderCategory.MIXED
    )
    home_venue = models.ForeignKey(
        "school_events.EventVenue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_home_teams",
    )
    roster_cap = models.PositiveSmallIntegerField(default=DEFAULT_ROSTER_CAP)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.FORMING
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["name"]
        unique_together = [("season", "name")]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.season_id})"


class CoachAssignment(models.Model):
    """Links a coach (User, optionally a TeacherProfile) to a team.

    Scopes a COACH's object-level authority: a coach only manages teams they
    are actively assigned to (analogous to evals.TeacherAssignment scoping a
    teacher to classrooms).
    """

    class Role(models.TextChoices):
        HEAD = "head", "Head coach"
        ASSISTANT = "assistant", "Assistant coach"
        MANAGER = "manager", "Team manager"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_coach_assignments",
    )
    team = models.ForeignKey(
        "athletics.Team", on_delete=models.CASCADE, related_name="coach_assignments"
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="athletics_coach_assignments",
    )
    teacher_profile = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="athletics_coach_assignments",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.HEAD)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "coach", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "coach"],
                condition=Q(is_active=True),
                name="uniq_active_coach_per_team",
            )
        ]

    def __str__(self) -> str:
        return f"coach {self.coach_id} -> team {self.team_id} ({self.role})"


__all__ = ["Team", "CoachAssignment"]
