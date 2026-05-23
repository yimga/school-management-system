"""
Wave 6/10 (v3.62.10 — 2026-05-22) — first-class `School.primary_language`.

Previously the per-school language pick from the signup form landed only in
`school.settings.localization.language_code` (a JSON path). This migration
promotes it to a first-class field so:

  - the lexicon cascade can resolve it in O(1) on every request
  - django-tenants schemas can index on it
  - admin filters / dashboards can sort by it
  - audits / reports can join on it

Idempotent: AddField only; reversible via migrate schools 0056.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0056_alter_school_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="primary_language",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Primary language of instruction (BCP-47 primary subtag "
                    "form: en/fr/zh-hans/ar/hi/ur/...). For multilingual "
                    "countries this drives the per-language education-system "
                    "overlay shown across the platform. Empty = use the "
                    "country's default language."
                ),
                max_length=16,
            ),
        ),
    ]
