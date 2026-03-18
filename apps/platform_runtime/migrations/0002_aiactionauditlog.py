# Phase 10 — 10.8: AI action audit trail

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0001_runtimedefaults"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIActionAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("action_type", models.CharField(db_index=True, max_length=80)),
                ("tenant_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("user_id", models.IntegerField(blank=True, db_index=True, null=True)),
                (
                    "request_id",
                    models.CharField(blank=True, db_index=True, max_length=64),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "AI action audit log",
                "verbose_name_plural": "AI action audit logs",
                "ordering": ["-created_at"],
            },
        ),
    ]
