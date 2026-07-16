"""Re-heal academics 0028 ``school_id`` columns on schemas that drifted post-0057.

Live 500: ``column academics_academicyear.school_id does not exist``. The
canonical repair ``apps.academics.schema_repair.ensure_academics_school_id_columns``
already ran once via ``0057_ensure_academics_school_id_columns`` — but a tenant
schema whose ``django_migrations`` records 0057 as applied can STILL miss the
columns if it was provisioned by cloning a recorded migration state without
executing the RunPython (or its migrate fell short). Because 0057 is recorded,
``migrate_schemas --tenant`` will not re-run it.

As a fresh graph leaf, this migration re-invokes the SAME idempotent canonical
helper on EVERY tenant schema at the next ``migrate_schemas --tenant`` — a no-op
where the columns already exist, a one-shot heal where they don't. It reuses the
helper rather than duplicating the ALTER logic so both heal points stay in sync.
Pure RunPython → no model-state change, so ``makemigrations --check`` stays clean.
"""

from django.db import migrations


def _ensure_columns(apps, schema_editor):
    from apps.academics.schema_repair import ensure_academics_school_id_columns

    ensure_academics_school_id_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0063_backfill_attendance_school"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
