# Typed operator deep links for orchestration workbench (SOT batch 32 #402).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0044_platform_operator_command_center_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorOrchestrationWorkbenchLink",
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
                        help_text="Relative path (e.g. /super/playbook-operator-hub/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="orchestration_workbench",
                        help_text="e.g. orchestration_workbench, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator orchestration workbench link",
                "verbose_name_plural": "Operator orchestration workbench links",
                "db_table": "platform_runtime_operatororchestrationworkbenchlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
