# RLS enable for tenant-scoped policies tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['policies_policybundle', 'policies_policydecisionlog', 'policies_policyrule', 'policies_scheduledpolicyoverride', 'policies_tenantblueprint', 'policies_tenantpolicyoverride']


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
        ("policies", "0007_policyrule_policydecisionlog_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
