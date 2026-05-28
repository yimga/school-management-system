"""v4.00.12 — RLS audit-pass migration.

Re-runs the gap-walk from migration 0058 so any tenant-scoped table shipped
between v4.00.0 and v4.00.12 that was RLS-enabled (via its own app
``enable_rls_postgresql`` migration) but never had a policy attached
(forgot the ``rls_policy_default_deny`` follow-up) gets the canonical
default-deny + tenant_id-match policy applied here.

Idempotent: tables that already have policies are skipped by virtue of
the LEFT JOIN filter. No-op on SQLite + when USE_DJANGO_TENANTS=True
(schema-per-tenant deployment).
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


def close_audit_gap(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for schema, table in _rls_tables_without_policies(cursor):
            if not _table_has_school_id_column(cursor, schema, table):
                continue
            policy_name = f"v4_00_12_default_deny_{table}"
            cursor.execute(_POLICY_SHAPE.format(name=policy_name, schema=schema, table=table))


def open_audit_gap(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT n.nspname, c.relname, p.polname
            FROM pg_policy p
            JOIN pg_class c ON c.oid = p.polrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE p.polname LIKE 'v4_00_12_default_deny_%%'
              AND n.nspname = current_schema()
            """
        )
        for schema, table, policy in cursor.fetchall():
            cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{schema}"."{table}";')


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0058_v4_rls_audit_attendance_grades"),
    ]
    operations = [
        migrations.RunPython(close_audit_gap, open_audit_gap),
    ]
