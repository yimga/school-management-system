"""Neutralize column-level defaults on RegionConfig so a row created without
explicit values does not silently inherit Cameroon-specific assumptions.

- default_currency: "XAF" -> "USD" (neutral platform default)
- grading_scale: "0-20" -> "0-100" (most common globally; per-country overrides set during onboarding)

Existing rows are untouched; this migration only changes the column default for future inserts.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0171_normalize_gilead_watermark_residue"),
    ]

    operations = [
        migrations.AlterField(
            model_name="regionconfig",
            name="default_currency",
            field=models.CharField(
                default="USD",
                help_text=(
                    "ISO currency code (USD, EUR, GBP, XAF, KES, NGN, etc.). "
                    "Set per-country during onboarding; USD is the neutral fallback."
                ),
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="regionconfig",
            name="grading_scale",
            field=models.CharField(
                choices=[
                    ("0-20", "Cameroon (0-20)"),
                    ("0-100", "US/UK (0-100)"),
                    ("0-10", "European (0-10)"),
                    ("a-f", "Letter Grade (A-F)"),
                    ("gpa", "GPA (0-4.0)"),
                ],
                default="0-100",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="regionconfig",
            name="academic_year_start_month",
            field=models.IntegerField(
                default=9,
                help_text=(
                    "Month when academic year starts (1-12). Northern hemisphere typically uses 9 "
                    "(September); the region engine overrides to 1 (January) for Southern hemisphere "
                    "countries during onboarding."
                ),
            ),
        ),
    ]
