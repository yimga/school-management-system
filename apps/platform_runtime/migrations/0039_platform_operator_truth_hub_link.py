# Typed operator deep links for Runtime truth hub (SOT §11.4 batch 19 #207).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0038_platform_operator_playbook_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorTruthHubLink",
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
                        help_text="Relative path (e.g. /super/phase-b-snapshot-diff/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="truth_hub",
                        help_text="e.g. truth_hub, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator truth hub link",
                "verbose_name_plural": "Operator truth hub links",
                "db_table": "platform_runtime_operatortruthhublink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
