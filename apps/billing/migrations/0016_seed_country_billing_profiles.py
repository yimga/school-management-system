# Data migration: seed a configurable CountryBillingProfile for every catalog
# country (~249) so pricing/payment-methods/cycles/tax are defined platform-wide,
# not just for a handful of markets. Depends on the siteconfig multiplier expansion
# so each profile picks up its country's market tier. Idempotent.

from django.db import migrations


def seed_profiles(apps, schema_editor):
    from apps.billing.country_profile_seed import seed_country_billing_profiles

    seed_country_billing_profiles(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0015_countrybillingprofile"),
        ("siteconfig", "0205_seed_all_country_multipliers"),
        # ensures CountryRegistry currencies are correct before profiles read them
        ("registries", "0011_seed_currency_country_registries"),
    ]

    operations = [
        migrations.RunPython(seed_profiles, noop),
    ]
