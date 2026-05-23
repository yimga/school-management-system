"""
Wave 8 (v3.62.8 2026-05-22) — add operator-edited override JSON to
CountryRegistry so admin UI edits land on top of the seed pack at the
service hot path (apps/siteconfig/country_localization_service.py).

Idempotent: AddField only; reversible via migrate registries 0004.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registries", "0004_tenant_attendance_fee_registries"),
    ]

    operations = [
        migrations.AddField(
            model_name="countryregistry",
            name="cockpit_override_payload",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Operator-edited overlay applied on top of the in-memory "
                    "country seed pack. Shape mirrors the country pack: "
                    "calendar_systems / school_types / education_levels / "
                    "terminology / languages. Lists override wholesale; "
                    "dicts merge one level deep. Empty dict = no override."
                ),
            ),
        ),
    ]
