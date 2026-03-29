# Typed operator deep links for migration cloud control plane (§11.4 batch 36).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0049_platform_operator_platform_hub_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorMigrationCloudLink",
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
                        help_text="Relative path (e.g. /super/migration/registry/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="super_migration_cloud",
                        help_text="e.g. super_migration_cloud, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator migration cloud link",
                "verbose_name_plural": "Operator migration cloud links",
                "db_table": "platform_runtime_operatormigrationcloudlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
