# Typed operator deep links for support mission control (SOT batch 27 #327).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0041_platform_operator_workflow_simulator_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorSupportDashboardLink",
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
                        help_text="Relative path (e.g. /super/pulse/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="support_dashboard",
                        help_text="e.g. support_dashboard, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator support dashboard link",
                "verbose_name_plural": "Operator support dashboard links",
                "db_table": "platform_runtime_operatorsupportdashboardlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
