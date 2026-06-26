# RLS enable for tenant-scoped metadata tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['metadata_dynamicfielddefinition', 'metadata_dynamicfieldvalue', 'metadata_entitystate', 'metadata_layoutdefinition', 'metadata_statemachinedefinition']


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
        ("metadata", "0012_metadata_eav_rls_policies"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
