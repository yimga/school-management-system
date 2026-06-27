# Data migration: make the currency + country registries durable on deploy.
#
# CurrencyRegistry (ISO 4217, ~195 entries incl. symbols/decimal_places) and
# CountryRegistry (ISO 3166, ~249 entries) were previously populated only by a
# manual command, so a fresh deploy had empty registries -> currency symbols fell
# back to bare codes and per-country currency resolved to USD. This seeds both at
# migrate time and backfills each country's default_currency from the canonical
# CLDR-derived map so the 250-country footprint resolves to real local currencies.
# Idempotent; reference data is never torn down on rollback (reverse = no-op).

from django.db import migrations


def seed(apps, schema_editor):
    from apps.registries.country_currency_map import backfill_country_registry_currencies
    from apps.registries.currency_seed import ensure_currency_registry_seed
    from apps.registries.services import ensure_country_registry_seed

    ensure_currency_registry_seed()
    ensure_country_registry_seed()
    backfill_country_registry_currencies(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("registries", "0010_rls_policy_default_deny"),
    ]

    operations = [
        migrations.RunPython(seed, noop),
    ]
