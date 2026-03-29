# Typed operator deep links for Phase B snapshot diff (SOT batch 23 #267).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0039_platform_operator_truth_hub_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorPhaseBLink",
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
                        help_text="Relative path (e.g. /super/runtime-truth-hub/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="phase_b",
                        help_text="e.g. phase_b, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator Phase B link",
                "verbose_name_plural": "Operator Phase B links",
                "db_table": "platform_runtime_operatorphaseblink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
