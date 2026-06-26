# RLS enable for tenant-scoped events tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "events_domainevent",
    "events_webhooksubscription",
    "events_eventsystemremediationaudit",
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
        ("events", "0006_rename_events_remed_school_created_idx_events_even_school__fae22a_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
