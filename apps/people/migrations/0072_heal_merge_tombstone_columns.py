"""Re-heal merge tombstone columns on schemas that drifted (0064/0068 family).

Legacy ``people_*`` tables in the public schema never receive
``migrate_schemas --tenant``. When the ORM gained ``TeacherProfile.merged_into``
(0068) those tables kept serving manager / identity bootstrap queries without
the column — ``ProgrammingError: column people_teacherprofile.merged_into_id
does not exist`` during ``ensure_all_user_identities``.

Pure RunPython (no model-state change), idempotent via ``schema_repair``.
"""

from django.db import migrations


def _heal(apps, schema_editor):
    from apps.people.schema_repair import ensure_people_merge_tombstone_columns

    ensure_people_merge_tombstone_columns()


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0071_backfill_enrollment_from_student_row"),
    ]

    operations = [
        migrations.RunPython(_heal, migrations.RunPython.noop),
    ]
