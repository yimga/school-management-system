# Data migration: re-run the curated CountryMultiplier seed after the Wave 30
# expansion (50 -> 143 curated markets). Idempotent update_or_create keyed on
# country_code: existing curated rows are refreshed, the ~90 newly-curated
# countries are upserted, and any that previously held the neutral 1.0x Zone-B
# backfill (from 0205) are corrected to their real income-banded PPP multiplier.

from django.db import migrations


def seed_expanded(apps, schema_editor):
    from apps.siteconfig.country_multiplier_seed import seed_country_multipliers

    seed_country_multipliers(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0207_seed_country_grading_profiles"),
    ]

    operations = [
        migrations.RunPython(seed_expanded, noop),
    ]
