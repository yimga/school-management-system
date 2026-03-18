# Trigger INSERT omitted correlation_id / request_meta → NOT NULL violations on audit_log.

from django.db import connection, migrations


def replace_audit_trigger_fn(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    from apps.people.repositories.audit_repository import create_audit_trigger_function

    with connection.cursor() as cursor:
        create_audit_trigger_function(cursor)


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0041_fix_audit_trigger_insert_old_values"),
    ]

    operations = [
        migrations.RunPython(replace_audit_trigger_fn, migrations.RunPython.noop),
    ]
