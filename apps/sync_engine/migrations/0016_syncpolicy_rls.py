# RLS for the new tenant-scoped sync_engine table.
#
# `sync_engine` is a SHARED app: one physical table discriminated by `school_id`. Every
# other tenant-scoped table in this app carries a policy (0008/0009 for the original
# seven, 0011 for SyncSchedule), so a new one arriving without it is a silent hole. It
# lands in the same wave as the model rather than as a follow-up nobody writes.
#
# SCOPE, stated because it is easy to over-read: `should_apply_rls` returns False when
# USE_DJANGO_TENANTS is on, so this is a NO-OP on the cloud, where isolation is
# schema-per-tenant and shared-app tables are guarded by application-level `school=`
# filtering instead. It is real on a sovereign box (Postgres, single-tenant), which is
# where a query that forgot its filter would otherwise be unguarded.
#
# Postgres-only by construction, which is also why the SQLite suite cannot prove it --
# that assertion belongs to CI on Postgres, not to a green local run.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "sync_engine_syncpolicy"
POLICY = "sync_engine_tenant_syncpolicy"
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;")
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY} ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def reverse_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")
        cursor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("sync_engine", "0015_syncpolicy"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls),
    ]
