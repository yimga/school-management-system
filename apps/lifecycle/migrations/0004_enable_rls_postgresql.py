# RLS enable for tenant-scoped lifecycle tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "lifecycle_schoollifecyclestage",
    "lifecycle_purgeoperation",
    "lifecycle_tenantimmutablesnapshot",
]


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
        ("lifecycle", "0003_tenantimmutablesnapshot"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
