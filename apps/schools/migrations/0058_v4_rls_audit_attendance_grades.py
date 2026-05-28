"""v4.00.0 — close the audit/attendance/grades RLS default-deny gap.

Migrations 0026 and 0048 shipped default-deny + FORCE for the first wave of
tables. This adds an *audit pass*: walks every public-schema table that is
RLS-enabled but has zero policies attached, and applies the canonical
default-deny + tenant_id-match shape. Pure-Python, idempotent, no-op on
SQLite and on USE_DJANGO_TENANTS=True.

The audit list is empty by design — we are NOT hard-coding table names here.
The runtime walks ``pg_policy`` to find the actual gap surface. This protects
against new tenant-scoped tables shipped between waves that forgot the
``rls_policy_default_deny`` per-app pattern.
"""

from __future__ import annotations

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls


_POLICY_SHAPE = """
    CREATE POLICY "{name}" ON "{schema}"."{table}"
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (
        current_setting('app.rls_bypass', true) = 'on'
        OR (
            current_setting('app.current_school_id', true) IS NOT NULL
            AND current_setting('app.current_school_id', true) <> ''
            AND school_id::text = current_setting('app.current_school_id', true)
        )
    );
"""


def _rls_tables_without_policies(cursor):
    cursor.execute(
        """
        SELECT n.nspname, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_policy p ON p.polrelid = c.oid
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = TRUE
          AND n.nspname = current_schema()
          AND p.oid IS NULL
        GROUP BY n.nspname, c.relname
        ORDER BY n.nspname, c.relname
        """
    )
    return cursor.fetchall()


def _table_has_school_id_column(cursor, schema: str, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = 'school_id'
        LIMIT 1
        """,
        [schema, table],
    )
    return cursor.fetchone() is not None


def close_default_deny_gap(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        gaps = _rls_tables_without_policies(cursor)
        for schema, table in gaps:
            if not _table_has_school_id_column(cursor, schema, table):
                continue
            policy_name = f"v4_default_deny_{table}"
            cursor.execute(_POLICY_SHAPE.format(name=policy_name, schema=schema, table=table))


def open_default_deny_gap(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT n.nspname, c.relname, p.polname
            FROM pg_policy p
            JOIN pg_class c ON c.oid = p.polrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE p.polname LIKE 'v4_default_deny_%%'
              AND n.nspname = current_schema()
            """
        )
        for schema, table, policy in cursor.fetchall():
            cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{schema}"."{table}";')


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0057_school_primary_language"),
    ]
    operations = [
        migrations.RunPython(close_default_deny_gap, open_default_deny_gap),
    ]
