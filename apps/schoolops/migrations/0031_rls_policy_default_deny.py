# RLS default-deny policy for this app's schoolops-owned tenant tables.
# Companion to 0030 (the app's paired enable/deny RLS step). PostgreSQL
# single-schema mode only; no-op under schema-per-tenant and SQLite.
#
# Same three tables as 0030 and the same reason for the scope: the legacy
# `schools_*` tables of models moved out of the `schools` app are owned by
# schools/0081_rls_backfill_unenumerated_tenant_tables, not here. The pre-fix
# version listed them under a wrong `schoolops_*` prefix that does not exist,
# which aborted `migrate` on a fresh single-schema Postgres database.
#
# The policy denies by default: access is allowed only when app.rls_bypass is on
# or app.current_school_id is set AND matches the row's school_id (NULL context =
# deny). This is the same USING clause schools/0081 applies platform-wide.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

SCHOOLOPS_OWNED_TABLES = [
    "schoolops_busboardingevent",
    "schoolops_bookableresource",
    "schoolops_resourcebooking",
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _existing_with_school_id(cursor, tables):
    cursor.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND n.nspname = current_schema()
          AND c.relname = ANY(%s)
          AND a.attname = 'school_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        [list(tables)],
    )
    return [row[0] for row in cursor.fetchall()]


def _assert_default_deny_policy(cursor, tables):
    for table in tables:
        policy = f"rls_tenant_{table}"
        # Idempotent + defensive: ensure RLS is on (0030 already did) then
        # (re)assert the default-deny policy.
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS {policy} ON "{table}";')
        cursor.execute(
            f"""
            CREATE POLICY {policy} ON "{table}"
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def apply_default_deny_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        _assert_default_deny_policy(cursor, _existing_with_school_id(cursor, SCHOOLOPS_OWNED_TABLES))


def reverse_default_deny_policy(apps, schema_editor):
    # Reversing this migration returns to 0030's state, which is the SAME
    # default-deny policy -- so re-assert it (a no-op in practice).
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        _assert_default_deny_policy(cursor, _existing_with_school_id(cursor, SCHOOLOPS_OWNED_TABLES))


class Migration(migrations.Migration):
    dependencies = [
        ("schoolops", "0030_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny_policy, reverse_default_deny_policy),
    ]
