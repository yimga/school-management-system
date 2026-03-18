# Phase 10 — 1.2: Runtime defaults (state-safe migration from SiteSettings)

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RuntimeDefaults",
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
                ("payload", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Runtime defaults",
                "verbose_name_plural": "Runtime defaults",
                "app_label": "platform_runtime",
            },
        ),
    ]
