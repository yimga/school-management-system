# Data migration: seed CountryMultiplier PPP bands for supported markets.

from django.db import migrations


def seed_ppp_rows(apps, schema_editor):
    from apps.siteconfig.country_multiplier_seed import seed_country_multipliers

    seed_country_multipliers(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0202_b2_sku_overrides_b4_holding_rollup"),
    ]

    operations = [
        migrations.RunPython(seed_ppp_rows, noop),
    ]
