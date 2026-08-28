"""Seed Alma / FACTS / Skyward connector profiles + mapping templates (2026-08-28)."""

from django.db import migrations


def seed_alma_facts_skyward(apps, schema_editor):
    from apps.migration_cloud.management.commands.seed_migration_connector_profiles import (
        seed_connector_profiles,
    )

    seed_connector_profiles(model=apps.get_model("migration_cloud", "MigrationConnectorProfile"))


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0048_quarantine_auto_audit_event_types"),
    ]

    operations = [
        migrations.RunPython(seed_alma_facts_skyward, migrations.RunPython.noop),
    ]
