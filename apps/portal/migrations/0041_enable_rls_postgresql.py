# RLS enable for portal tenant-scoped tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

PORTAL_TABLES = [
    "portal_portalfeatureitem",
]


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in PORTAL_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in PORTAL_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0040_kbarticle_linked_office_document"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
