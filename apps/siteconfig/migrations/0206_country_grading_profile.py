# Globalization program 2.1 — country -> grading scale as DATA.
#
# Platform-catalog (SHARED / public schema) table, same shape as CountryMultiplier
# and SubdivisionTaxRate. Deliberately carries NO foreign key to evals.GradingScale:
# apps.evals is a TENANT app and a SHARED -> TENANT FK is a known deploy blocker
# (migrate_schemas --shared fails on a fresh database).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0205_seed_all_country_multipliers"),
    ]

    operations = [
        migrations.CreateModel(
            name="CountryGradingProfile",
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
                (
                    "country_code",
                    models.CharField(
                        help_text="ISO 3166-1 alpha-2/3 (matches CountryMultiplier).",
                        max_length=3,
                        unique=True,
                    ),
                ),
                (
                    "scale_type",
                    models.CharField(
                        help_text=(
                            "evals.GradingScale.ScaleType value used as this country's "
                            "default grading scale (e.g. french_0_20, german_1_6, "
                            "cbse_10, numeric_1_5)."
                        ),
                        max_length=50,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        help_text="Country name (display only).",
                        max_length=120,
                    ),
                ),
                (
                    "notes",
                    models.CharField(
                        blank=True,
                        help_text="Provenance / caveat for this mapping (e.g. 'Abitur 1–6').",
                        max_length=200,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Inactive rows are ignored by the resolver (falls through "
                            "to the preset engine)."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Country grading profile",
                "verbose_name_plural": "Country grading profiles",
                "ordering": ["country_code"],
            },
        ),
    ]
