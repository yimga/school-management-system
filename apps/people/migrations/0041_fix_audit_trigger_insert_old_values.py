# INSERT rows used NULL for old_values; audit_log.old_values is NOT NULL → seeding failed.

from django.db import connection, migrations


def replace_audit_trigger_fn(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    from apps.people.repositories.audit_repository import create_audit_trigger_function

    with connection.cursor() as cursor:
        create_audit_trigger_function(cursor)


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0040_teacherprofile_updated_at"),
    ]

    operations = [
        migrations.RunPython(replace_audit_trigger_fn, migrations.RunPython.noop),
    ]
