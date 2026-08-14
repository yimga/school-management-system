"""Revive the dead RegionConfig.student_id_format hook.

``RegionConfig.student_id_format`` was the intended per-region admission-number
template, but it shipped as a blank field nothing ever seeded — so the country
layer of the admission cascade was empty and every tenant fell back to the
generic format. This fills a country-appropriate default on every existing region
row that has none (idempotent: only blanks are touched; an admin/region edit is
never overwritten). Values are inlined here so the migration stays frozen.
"""

from django.db import migrations

_SLASH = "{school_code}/{year_2digit}/{seq_4digit}"
_DASH = "{school_code}-{year_2digit}-{seq_4digit}"
_COMPACT = "{year_2digit}{school_code}{seq_4digit}"
_SEQ_YEAR = "{year_2digit}{seq_4digit}"

# RegionConfig.code is ISO alpha-3.
_TEMPLATES = {
    "CMR": _SLASH, "NGA": _SLASH, "GHA": _SLASH, "KEN": _SLASH,
    "UGA": _SLASH, "TZA": _SLASH, "IND": _SLASH, "ZAF": _SLASH,
    "GBR": _COMPACT, "FRA": _DASH, "DEU": _DASH,
    "USA": _SEQ_YEAR, "CAN": _SEQ_YEAR,
}
_GENERIC = _COMPACT


def seed_region_admission_templates(apps, schema_editor):
    RegionConfig = apps.get_model("siteconfig", "RegionConfig")
    for region in RegionConfig.objects.all():
        if (getattr(region, "student_id_format", "") or "").strip():
            continue  # an explicit value (admin edit / prior seed) always wins
        code = (region.code or "").strip().upper()
        region.student_id_format = _TEMPLATES.get(code, _GENERIC)
        region.save(update_fields=["student_id_format"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0208_seed_expanded_country_multipliers"),
    ]
    operations = [
        migrations.RunPython(seed_region_admission_templates, noop_reverse),
    ]
