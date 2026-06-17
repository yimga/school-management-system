from django.db import migrations


def _ensure_columns(apps, schema_editor):
    # Idempotent heal for tenant schemas that never received 0022/0023's
    # client_offline_id column (+ partial unique index) on schools_visitorcheckin.
    # Same drift family as people/0059. Runs per-tenant under
    # `migrate_schemas --tenant` (predeploy) and at provision time; no-op on
    # healthy schemas; safe whether 0022/0023 are applied/fake-applied/unapplied.
    from apps.schoolops.schema_repair import ensure_visitorcheckin_offline_id_column

    ensure_visitorcheckin_offline_id_column()


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0026_stop_latitude_stop_longitude"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
