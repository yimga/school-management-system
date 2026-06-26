# RLS enable for tenant-scoped migration_cloud tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['migration_cloud_migrationasset', 'migration_cloud_migrationbundle', 'migration_cloud_migrationidmapping']


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
        ("migration_cloud", "0029_extend_audit_event_type_lifecycle"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
