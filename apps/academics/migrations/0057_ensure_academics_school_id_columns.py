from django.db import migrations


def _ensure_columns(apps, schema_editor):
    # Idempotent heal for tenant schemas missing academics 0028 ``school_id``
    # columns (common when provision reused a schema without re-migrating).
    from apps.academics.schema_repair import ensure_academics_school_id_columns

    ensure_academics_school_id_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0056_remove_scheduleentry_uniq_schedentry_teacher_slot_shift_and_more"),
        ("schools", "0061_alter_school_governance_help_text"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
