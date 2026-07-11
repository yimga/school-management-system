"""Seed the platform-wide Migration Cloud connector registry.

``0025_migration_cloud_connectors`` created ``MigrationConnectorProfile`` but
never populated it, and the ``seed_migration_connector_profiles`` management
command was wired into no deploy step — so a freshly-migrated database had an
empty registry and the tenant "Connect source platform" dropdown rendered zero
options. This data migration seeds the registry as part of ``migrate`` /
``migrate_schemas --shared`` so every environment gets the profiles. Idempotent
(``update_or_create`` per key) and re-run-safe; the reverse is a no-op so a
rollback never deletes an operator's registry rows.
"""

from __future__ import annotations

from django.db import migrations


def _seed_profiles(apps, schema_editor):
    # Function-local import keeps the migration module free of live-model
    # imports; the seed data + upsert live in ONE place (the command module).
    from apps.migration_cloud.management.commands.seed_migration_connector_profiles import (
        seed_connector_profiles,
    )

    model = apps.get_model("migration_cloud", "MigrationConnectorProfile")
    seed_connector_profiles(model)


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0034_idmapping_domain_in_identity"),
    ]

    operations = [
        migrations.RunPython(_seed_profiles, migrations.RunPython.noop),
    ]
