# Data migration: expand CountryMultiplier from the curated markets to the FULL
# ISO catalog (~249 countries) so every country has a PPP band out of the box.
# Curated rows keep their tuned multiplier/tax; the rest get a neutral 1.0x Zone-B
# default an operator can refine. Idempotent (update_or_create / existence check).

from django.db import migrations


def seed_all(apps, schema_editor):
    from apps.siteconfig.country_multiplier_seed import expand_seed_to_all_countries

    expand_seed_to_all_countries(using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0204_alter_plan_options_alter_planaddon_options_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_all, noop),
    ]
