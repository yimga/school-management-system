# RLS enable for tenant-scoped school_events tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

SCHOOL_EVENTS_TABLES = [
    "school_events_eventvenue",
    "school_events_eventsponsor",
    "school_events_schoolevent",
]


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SCHOOL_EVENTS_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SCHOOL_EVENTS_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("school_events", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
