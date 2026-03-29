# Typed operator deep links for super analytics overview (SOT batch 35 #447).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0047_platform_operator_super_schools_list_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorSuperAnalyticsOverviewLink",
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
                        help_text="Relative path (e.g. /super/usage/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="super_analytics_overview",
                        help_text="e.g. super_analytics_overview, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator super analytics overview link",
                "verbose_name_plural": "Operator super analytics overview links",
                "db_table": "platform_runtime_operatorsuperanalyticsoverviewlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
