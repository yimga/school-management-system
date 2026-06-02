# Generated for Workflow Progress 10x waves 2–4.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0078_tenant_reactivation_attempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowAutopilotPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workflow_key", models.CharField(db_index=True, max_length=80)),
                ("tenant_schema", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("allowed_auto_fix_kinds", models.JSONField(blank=True, default=list)),
                ("enabled", models.BooleanField(default=False)),
                ("promoted_from_successes", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Workflow autopilot policy",
                "verbose_name_plural": "Workflow autopilot policies",
            },
        ),
        migrations.CreateModel(
            name="WorkflowAutopilotApplyLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.PositiveIntegerField(db_index=True)),
                ("workflow_key", models.CharField(db_index=True, max_length=80)),
                ("auto_fix_kind", models.CharField(max_length=64)),
                ("outcome", models.CharField(default="applied", max_length=32)),
                ("actor_user_id", models.CharField(blank=True, default="", max_length=40)),
                ("autopilot", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Workflow autopilot apply log",
                "verbose_name_plural": "Workflow autopilot apply logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="WorkflowDurationStat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workflow_key", models.CharField(max_length=80, unique=True)),
                ("sample_count", models.PositiveIntegerField(default=0)),
                ("p50_seconds", models.PositiveIntegerField(default=0)),
                ("p95_seconds", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Workflow duration stat",
                "verbose_name_plural": "Workflow duration stats",
            },
        ),
        migrations.CreateModel(
            name="WorkflowSlaBreach",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.PositiveIntegerField(db_index=True)),
                ("workflow_key", models.CharField(db_index=True, max_length=80)),
                ("tenant_schema", models.CharField(blank=True, default="", max_length=64)),
                ("slo_seconds", models.PositiveIntegerField()),
                ("actual_seconds", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Workflow SLA breach",
                "verbose_name_plural": "Workflow SLA breaches",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="workflowautopilotpolicy",
            constraint=models.UniqueConstraint(
                fields=("workflow_key", "tenant_schema"),
                name="uniq_workflow_autopilot_policy_scope",
            ),
        ),
    ]
