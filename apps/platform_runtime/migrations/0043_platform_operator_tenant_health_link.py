# Typed operator deep links for tenant health monitor (SOT batch 30 #372).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0042_platform_operator_support_dashboard_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorTenantHealthLink",
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
                        default="tenant_health",
                        help_text="e.g. tenant_health, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator tenant health link",
                "verbose_name_plural": "Operator tenant health links",
                "db_table": "platform_runtime_operatortenanthealthlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
