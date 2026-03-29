# Typed operator deep links for platform operator hub (SOT batch 35 #447 extension / #449).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0048_platform_operator_super_analytics_overview_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorPlatformHubLink",
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
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("label", models.CharField(max_length=128)),
                (
                    "href",
                    models.CharField(
                        help_text="Relative path (e.g. /super/command-center/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="super_platform_operator_hub",
                        help_text="e.g. super_platform_operator_hub, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator platform hub link",
                "verbose_name_plural": "Operator platform hub links",
                "db_table": "platform_runtime_operatorplatformhublink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
