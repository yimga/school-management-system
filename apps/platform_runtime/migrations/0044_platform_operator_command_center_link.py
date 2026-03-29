# Typed operator deep links for mission / command center (SOT batch 31 #387).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0043_platform_operator_tenant_health_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorCommandCenterLink",
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
                        default="command_center",
                        help_text="e.g. command_center, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator command center link",
                "verbose_name_plural": "Operator command center links",
                "db_table": "platform_runtime_operatorcommandcenterlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
