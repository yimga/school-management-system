from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "platform_runtime",
            "0005_alter_runtimedefaults_cache_rankings_interval_minutes",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformEventLog",
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
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "tenant_id",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=64
                    ),
                ),
                (
                    "school_id",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=40
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=128
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Platform event log",
                "verbose_name_plural": "Platform event logs",
                "ordering": ["-created_at"],
            },
        ),
    ]
