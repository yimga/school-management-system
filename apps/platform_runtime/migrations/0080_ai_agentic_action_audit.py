"""AIAgenticActionAudit — durable append-only sink for the agentic Phase-1 rollout."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0079_workflow_10x_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIAgenticActionAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audit_id", models.CharField(db_index=True, max_length=32, unique=True)),
                ("tenant_id", models.CharField(blank=True, default="", max_length=128)),
                ("actor_user_id_hash", models.CharField(blank=True, default="", max_length=16)),
                ("confirmed_by_hash", models.CharField(blank=True, default="", max_length=16)),
                ("action", models.CharField(max_length=128)),
                ("impact", models.CharField(blank=True, default="", max_length=16)),
                ("params_hash", models.CharField(blank=True, default="", max_length=32)),
                ("executed", models.BooleanField(default=False)),
                (
                    "outcome",
                    models.CharField(
                        choices=[("ok", "Ok"), ("blocked", "Blocked"), ("error", "Error")],
                        default="ok",
                        max_length=16,
                    ),
                ),
                ("blocked_reason", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "AI agentic action audit",
                "verbose_name_plural": "AI agentic action audits",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="aiagenticactionaudit",
            index=models.Index(fields=["tenant_id", "created_at"], name="agentic_audit_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="aiagenticactionaudit",
            index=models.Index(fields=["action", "created_at"], name="agentic_audit_action_idx"),
        ),
    ]
