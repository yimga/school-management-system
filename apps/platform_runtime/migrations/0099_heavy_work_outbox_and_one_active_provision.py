"""Create HeavyWorkOutbox + one-active provision WorkflowRun constraint.

Pre-constraint cleanup cancels duplicate running/stuck provision runs so the
partial unique can apply on existing databases.
"""

import uuid

from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def _cancel_duplicate_active_provisions(apps, schema_editor):
    WorkflowRun = apps.get_model("platform_runtime", "WorkflowRun")
    keys = ("tenant_school_provision", "tenant_school_create")
    seen = {}
    # tenant-isolation-allow: platform-migration-dedupe-active-provision-runs-global
    qs = (
        WorkflowRun.objects.filter(
            workflow_key__in=keys,
            status__in=("running", "stuck"),
        )
        .exclude(school_id="")
        .order_by("school_id", "workflow_key", "-started_at", "-id")
    )
    cancel_ids = []
    for run in qs.iterator():
        pair = (run.school_id, run.workflow_key)
        if pair in seen:
            cancel_ids.append(run.pk)
        else:
            seen[pair] = run.pk
    if cancel_ids:
        WorkflowRun.objects.filter(pk__in=cancel_ids).update(
            status="cancelled",
            ended_at=timezone.now(),
        )


def _noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0098_seed_stuck_autopilot_policies"),
    ]

    operations = [
        migrations.CreateModel(
            name="HeavyWorkOutbox",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("kind", models.CharField(db_index=True, max_length=48)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "school_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=40),
                ),
                (
                    "tenant_schema",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                (
                    "bundle_id",
                    models.PositiveIntegerField(blank=True, db_index=True, null=True),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "idempotency_key",
                    models.CharField(blank=True, db_index=True, default="", max_length=160),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Heavy work outbox",
                "verbose_name_plural": "Heavy work outbox",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="heavyworkoutbox",
            index=models.Index(
                fields=["status", "created_at"], name="hwo_status_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="heavyworkoutbox",
            index=models.Index(
                fields=["kind", "status", "created_at"],
                name="hwo_kind_status_created_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="heavyworkoutbox",
            constraint=models.UniqueConstraint(
                condition=Q(
                    kind="provision_school", status__in=["pending", "processing"]
                )
                & ~Q(school_id=""),
                fields=("kind", "school_id"),
                name="uniq_active_provision_outbox_per_school",
            ),
        ),
        migrations.AddConstraint(
            model_name="heavyworkoutbox",
            constraint=models.UniqueConstraint(
                condition=~Q(idempotency_key="")
                & Q(status__in=["pending", "processing"]),
                fields=("idempotency_key",),
                name="uniq_heavy_work_idempotency_active",
            ),
        ),
        migrations.RunPython(_cancel_duplicate_active_provisions, _noop_reverse),
        migrations.AddConstraint(
            model_name="workflowrun",
            constraint=models.UniqueConstraint(
                condition=Q(status__in=["running", "stuck"])
                & ~Q(school_id="")
                & Q(
                    workflow_key__in=[
                        "tenant_school_provision",
                        "tenant_school_create",
                    ]
                ),
                fields=("school_id", "workflow_key"),
                name="uniq_active_provision_run_per_school",
            ),
        ),
    ]
