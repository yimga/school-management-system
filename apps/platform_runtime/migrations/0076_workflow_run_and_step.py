"""WorkflowRun + WorkflowStep models for the platform-wide Workflow Progress Bus (v4.00.96).

Pure CreateModel — no data migration, no AlterField on existing rows.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0075_ensure_admin_operator_profile"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workflow_key", models.CharField(db_index=True, max_length=80)),
                ("workflow_label", models.CharField(blank=True, default="", max_length=160)),
                ("tenant_schema", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("school_id", models.CharField(blank=True, db_index=True, default="", max_length=40)),
                ("actor_user_id", models.CharField(blank=True, db_index=True, default="", max_length=40)),
                ("actor_label", models.CharField(blank=True, default="", max_length=120)),
                ("status", models.CharField(
                    choices=[
                        ("running", "Running"),
                        ("succeeded", "Succeeded"),
                        ("failed", "Failed"),
                        ("stuck", "Stuck"),
                        ("cancelled", "Cancelled"),
                    ],
                    db_index=True, default="running", max_length=16,
                )),
                ("total_steps", models.PositiveSmallIntegerField(default=0)),
                ("current_step_ordinal", models.PositiveSmallIntegerField(default=0)),
                ("current_step_name", models.CharField(blank=True, default="", max_length=80)),
                ("expected_duration_seconds", models.PositiveIntegerField(default=30)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("last_heartbeat_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("idempotency_key", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("payload_summary", models.JSONField(blank=True, default=dict)),
                ("error_summary", models.JSONField(blank=True, default=dict)),
                ("suggested_remediation", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "Workflow run",
                "verbose_name_plural": "Workflow runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="workflowrun",
            index=models.Index(
                fields=["tenant_schema", "status", "-started_at"],
                name="wfr_tenant_status_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowrun",
            index=models.Index(
                fields=["workflow_key", "-started_at"],
                name="wfr_workflow_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowrun",
            index=models.Index(
                fields=["actor_user_id", "-started_at"],
                name="wfr_actor_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowrun",
            index=models.Index(
                fields=["last_heartbeat_at"],
                name="wfr_heartbeat_idx",
            ),
        ),
        migrations.CreateModel(
            name="WorkflowStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ordinal", models.PositiveSmallIntegerField()),
                ("name", models.CharField(max_length=80)),
                ("label", models.CharField(blank=True, default="", max_length=160)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("running", "Running"),
                        ("done", "Done"),
                        ("failed", "Failed"),
                        ("skipped", "Skipped"),
                    ],
                    db_index=True, default="pending", max_length=12,
                )),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("payload_summary", models.JSONField(blank=True, default=dict)),
                ("error_text", models.CharField(blank=True, default="", max_length=512)),
                ("run", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="steps",
                    to="platform_runtime.workflowrun",
                )),
            ],
            options={
                "verbose_name": "Workflow step",
                "verbose_name_plural": "Workflow steps",
                "ordering": ["run_id", "ordinal"],
            },
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.UniqueConstraint(
                fields=("run", "ordinal"),
                name="wfs_unique_run_ordinal",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowstep",
            index=models.Index(
                fields=["run", "status"],
                name="wfs_run_status_idx",
            ),
        ),
    ]
