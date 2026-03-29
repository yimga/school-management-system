# Typed operator deep links for control plane home / super dashboard (SOT batch 33 #417).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0045_platform_operator_orchestration_workbench_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorSuperDashboardLink",
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
                        default="super_dashboard",
                        help_text="e.g. super_dashboard, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator super dashboard link",
                "verbose_name_plural": "Operator super dashboard links",
                "db_table": "platform_runtime_operatorsuperdashboardlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
