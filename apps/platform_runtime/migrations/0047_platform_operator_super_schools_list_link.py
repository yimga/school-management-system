# Typed operator deep links for super schools list (SOT batch 34 #432).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0046_platform_operator_super_dashboard_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformOperatorSuperSchoolsListLink",
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
                        help_text="Relative path (e.g. /super/tenant-health/) or absolute URL.",
                        max_length=512,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        default="super_schools_list",
                        help_text="e.g. super_schools_list, admin, runbook",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Operator super schools list link",
                "verbose_name_plural": "Operator super schools list links",
                "db_table": "platform_runtime_operatorsuperschoolslistlink",
                "ordering": ("sort_order", "slug"),
            },
        ),
    ]
