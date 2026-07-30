from django.db import migrations


def _ensure_columns(apps, schema_editor):
    # Idempotent heal for schemas that never received 0070's client_offline_id
    # column (+ the partial unique indexes) on schools_advancementgift /
    # schools_inkinddonation. Same drift family as people/0059 + schoolops/0027.
    # apps.schools is SHARED, so this runs in the public schema under
    # `migrate_schemas --shared` (predeploy); no-op on healthy schemas; safe
    # whether 0070 is applied/fake-applied/unapplied.
    from apps.schools.schema_repair import ensure_advancement_offline_id_columns

    ensure_advancement_offline_id_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0081_rls_backfill_unenumerated_tenant_tables"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
