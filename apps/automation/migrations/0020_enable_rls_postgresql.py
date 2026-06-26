# RLS enable for tenant-scoped automation tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['automation_automationapprovalqueue', 'automation_automationexecutionlog', 'automation_migrationquarantinerecord', 'automation_migrationrun', 'automation_workflow']


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0019_workflow_versioning_v2"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
