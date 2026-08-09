from django.db import migrations


def _ensure_columns(apps, schema_editor):
    # Idempotent heal for tenant schemas that never physically received 0073's
    # ``client_offline_id`` column (+ per-school partial unique index) on the
    # academics_classroom / academics_attendance tables. Runs per-tenant under
    # ``migrate_schemas --tenant`` in predeploy and per-tenant at provision time.
    # No-op on healthy schemas; safe whether 0073 is applied, fake-applied, or
    # unapplied in this schema (ADD COLUMN / CREATE INDEX ... IF NOT EXISTS).
    from apps.academics.schema_repair import ensure_academics_offline_sync_columns

    ensure_academics_offline_sync_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0073_attendance_classroom_client_offline_id"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
