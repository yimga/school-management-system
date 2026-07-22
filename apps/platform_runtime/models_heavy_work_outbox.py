"""Durable outbox for multi-minute work that must never own an HTTP thread.

Mirrors the DomainEvent outbox shape: PENDING → PROCESSING → SUCCEEDED|FAILED,
with Celery beat + in-process /health/ drain. Daemon threads are only used to
kick the drain when no worker is available — the row itself survives deploy/OOM.
"""

from __future__ import annotations

import logging
import uuid

from django.db import models
from django.db.models import Q

logger = logging.getLogger(__name__)


class HeavyWorkOutbox(models.Model):
    """One durable unit of heavy work (provision, schema heal, MC advance/apply)."""

    class Kind(models.TextChoices):
        PROVISION_SCHOOL = "provision_school", "Provision school"
        HEAL_TENANT_SCHEMA = "heal_tenant_schema", "Heal tenant schema drift"
        RUN_TENANT_MIGRATIONS = "run_tenant_migrations", "Run tenant migrations"
        MC_ADVANCE_BUNDLE = "mc_advance_bundle", "Migration Cloud advance"
        MC_APPLY_BUNDLE = "mc_apply_bundle", "Migration Cloud apply"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=48, choices=Kind.choices, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    school_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    tenant_schema = models.CharField(max_length=64, blank=True, default="", db_index=True)
    bundle_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "platform_runtime"
        ordering = ["created_at"]
        verbose_name = "Heavy work outbox"
        verbose_name_plural = "Heavy work outbox"
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="hwo_status_created_idx",
            ),
            models.Index(
                fields=["kind", "status", "created_at"],
                name="hwo_kind_status_created_idx",
            ),
        ]
        constraints = [
            # Collapse concurrent provision kicks for the same school.
            models.UniqueConstraint(
                fields=["kind", "school_id"],
                condition=Q(
                    kind="provision_school",
                    status__in=["pending", "processing"],
                )
                & ~Q(school_id=""),
                name="uniq_active_provision_outbox_per_school",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key="")
                & Q(status__in=["pending", "processing"]),
                name="uniq_heavy_work_idempotency_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}[{self.status}] {self.id}"
