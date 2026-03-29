# Typed operator deep links for workflow simulator (SOT batch 24 #282).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0040_platform_operator_phase_b_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorWorkflowSimulatorLink",
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
                        help_text="Relative path (e.g. /super/runtime-inspector/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="workflow_simulator",
                        help_text="e.g. workflow_simulator, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator workflow simulator link",
                "verbose_name_plural": "Operator workflow simulator links",
                "db_table": "platform_runtime_operatorworkflowsimulatorlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
