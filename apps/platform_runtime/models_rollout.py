"""Wave D — G3: platform schema rollout audit trail.

The platform runs on a shared-schema + RLS Postgres deployment (with a
minority of tenants on ``School.dedicated_db_alias`` overrides). Wave D
does NOT introduce per-tenant schema migrations — there are no per-tenant
schemas — but it DOES give us:

* a single auditable record per migration apply (start, finish, status,
  who ran it, whether destructive flags were required);
* a per-DB-alias result row so multi-database tenants get explicit
  visibility into which replica/alias has caught up;
* a safety gate that refuses destructive migrations (NOT NULL adds,
  column renames, DROP) unless ``--dangerous`` was passed.

This is the audit + safety layer that makes the standard ``migrate``
command safe to run at scale. The coordinator lives in
``apps.platform_runtime.schema_rollout``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


ROLLOUT_STATUSES: tuple[tuple[str, str], ...] = (
    ("pending", "Pending"),
    ("running", "Running"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("partial", "Partial (some aliases failed)"),
    ("dry_run", "Dry run (no changes)"),
)
ROLLOUT_STATUS_CODES: frozenset[str] = frozenset(code for code, _ in ROLLOUT_STATUSES)


PER_DB_STATUSES: tuple[tuple[str, str], ...] = (
    ("pending", "Pending"),
    ("applied", "Applied"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
)


class SchemaRollout(models.Model):
    """One platform-migration apply cycle."""

    target = models.CharField(
        max_length=200,
        help_text="Migration target label, e.g. 'apps.schools.0048' or 'all'.",
    )
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_rollouts",
    )
    status = models.CharField(
        max_length=16, choices=ROLLOUT_STATUSES, default="pending", db_index=True
    )
    dangerous_acknowledged = models.BooleanField(
        default=False,
        help_text="Did the operator explicitly pass --dangerous?",
    )
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Free-form context from the operator.")
    summary = models.JSONField(default=dict, blank=True, help_text="Captured stdout/stderr keyed by alias.")

    class Meta:
        verbose_name = "Schema rollout"
        verbose_name_plural = "Schema rollouts"
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.target} ({self.status})"

    @property
    def duration_seconds(self) -> int | None:
        if self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds())


class SchemaRolloutAlias(models.Model):
    """One ``(rollout, db_alias)`` result row."""

    rollout = models.ForeignKey(
        SchemaRollout,
        on_delete=models.CASCADE,
        related_name="alias_results",
    )
    db_alias = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=PER_DB_STATUSES, default="pending")
    error_text = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Schema rollout alias result"
        verbose_name_plural = "Schema rollout alias results"
        constraints = [
            models.UniqueConstraint(
                fields=["rollout", "db_alias"],
                name="uniq_rollout_alias",
            ),
        ]
        ordering = ("rollout_id", "db_alias")

    def __str__(self) -> str:
        return f"{self.rollout_id}·{self.db_alias}·{self.status}"
