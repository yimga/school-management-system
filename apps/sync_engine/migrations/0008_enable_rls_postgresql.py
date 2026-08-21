# RLS ENABLE + FORCE for tenant-scoped sync_engine tables (PostgreSQL only).
#
# SyncApplyLedger / EdgeSyncRun / EdgeSyncCursor / EdgeSyncDirective live in the
# SHARED/public schema, discriminated by school_id. Creating migrations 0001–0007
# depend on schools/0083, so both global FORCE sweeps (0048, 0083) and the 0081
# backfill already ran before these tables existed. Without this pair the
# table-owner role (Django) would bypass any later policy.
#
# No-op on SQLite and under USE_DJANGO_TENANTS=True (schema-per-tenant).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "sync_engine_syncapplyledger",
    "sync_engine_edgesyncrun",
    "sync_engine_edgesynccursor",
    "sync_engine_edgesyncdirective",
    "sync_engine_synctombstone",
    "sync_engine_syncbundlereceipt",
    "sync_engine_syncfiletransfer",
]


def enable_and_force_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def unforce_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("sync_engine", "0007_bundle_receipt_and_file_transfer"),
    ]

    operations = [
        migrations.RunPython(enable_and_force_rls, unforce_rls),
    ]
