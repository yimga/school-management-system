# RLS for the new tenant-scoped sync_engine table.
#
# `sync_engine` is a SHARED app: one physical table discriminated by `school_id`. Under
# USE_DJANGO_TENANTS that means every tenant's schedule rules live side by side in
# `public`, so row-level security is the ONLY thing keeping one school's configuration
# out of another's queries. Every other table in this app got it in 0008/0009; a new one
# arriving without it would be a silent hole, so it lands in the same migration as the
# model rather than as a follow-up nobody writes.
#
# Postgres-only by construction (`should_apply_rls` is False on SQLite), which is exactly
# why this cannot be proven by the SQLite suite — the assertion that belongs to CI on
# Postgres, not to a green local run.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "sync_engine_syncschedule"
POLICY = "sync_engine_tenant_syncschedule"
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
        ("sync_engine", "0010_syncschedule"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls),
    ]
