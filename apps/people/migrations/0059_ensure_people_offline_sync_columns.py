from django.db import migrations


def _ensure_columns(apps, schema_editor):
    # Idempotent heal for tenant schemas that never received 0057's
    # ``client_offline_id`` column (+ partial unique index). Runs per-tenant under
    # ``migrate_schemas --tenant`` in predeploy and per-tenant at provision time.
    # No-op on healthy schemas; safe whether 0057 is applied, fake-applied, or
    # unapplied in this schema (ADD COLUMN / CREATE INDEX … IF NOT EXISTS).
    from apps.people.schema_repair import ensure_people_offline_sync_columns

    ensure_people_offline_sync_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0058_delete_notificationpreference"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
