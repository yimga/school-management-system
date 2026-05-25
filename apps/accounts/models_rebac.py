"""Postgres relationship tuples for lightweight ReBAC (batch 1507)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class RelationshipTuple(models.Model):
    """
    (school, subject, relation, object) edge stored in Postgres.

    Subject is typically ``user:<pk>``. Objects include ``school``, ``student``,
    ``permission``, ``subject_assignment``, ``classroom``.
    """

    class Source(models.TextChoices):
        MEMBERSHIP = "membership", "School membership"
        GUARDIAN = "guardian", "StudentGuardian"
        TEACHER_ASSIGNMENT = "teacher_assignment", "TeacherAssignment"
        ACCESS_ROLE = "access_role", "User.roles M2M"
        TEMPORARY_GRANT = "temporary_grant", "TemporaryRoleGrant"
        DIRECT_PERMISSION = "direct_permission", "User.feature_permissions"
        BACKFILL = "backfill", "Management command backfill"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="relationship_tuples",
    )
    subject_type = models.CharField(max_length=32, db_index=True)
    subject_id = models.CharField(max_length=64, db_index=True)
    relation = models.CharField(max_length=48, db_index=True)
    object_type = models.CharField(max_length=32, db_index=True)
    object_id = models.CharField(max_length=128, db_index=True)
    source = models.CharField(
        max_length=32,
        choices=Source.choices,
        default=Source.BACKFILL,
        db_index=True,
    )
    source_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Stable idempotency key for writers (e.g. membership:12).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_relationship_tuple"
        ordering = ["school_id", "subject_type", "subject_id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "school",
                    "subject_type",
                    "subject_id",
                    "relation",
                    "object_type",
                    "object_id",
                ],
                name="uniq_relationship_tuple_edge",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "subject_type", "subject_id", "relation"],
                name="idx_rebac_subject_lookup",
            ),
            models.Index(
                fields=["school", "object_type", "object_id", "relation"],
                name="idx_rebac_object_lookup",
            ),
            models.Index(fields=["school", "source", "source_key"], name="idx_rebac_source"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.subject_type}:{self.subject_id}#{self.relation}@"
            f"{self.object_type}:{self.object_id} (school={self.school_id})"
        )


class OfflineAccessIntent(models.Model):
    """
    Low-risk IAM intents queued offline — applied only after server ``check()``.

    Never used for role grants or admin elevation.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"

    class IntentType(models.TextChoices):
        REQUEST_ACCESS = "iam.request_access", "Request access to capability"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offline_access_intents",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="offline_access_intents",
    )
    intent_type = models.CharField(
        max_length=32,
        choices=IntentType.choices,
        default=IntentType.REQUEST_ACCESS,
    )
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    server_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_offline_access_intent"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="uniq_offline_access_intent_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"OfflineAccessIntent {self.pk} {self.intent_type} ({self.status})"
