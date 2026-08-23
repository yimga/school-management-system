"""Enable RLS on the advancement/grant child tables (companion to 0085).

The table names are LITERALS on purpose: ``scripts/scan_rls_table_coverage.py``
is a static AST scan for table-name literals inside ``*rls*`` migrations, so a
registry walk here would leave that gate reporting a gap forever. Same shape and
same ``USING_CLAUSE`` as ``0081_rls_backfill_unenumerated_tenant_tables``.

No-op under schema-per-tenant: ``apps/schools/rls.py::should_apply_rls`` returns
False when ``USE_DJANGO_TENANTS`` is set, because isolation comes from the schema.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "schools_advancementgift",
    "schools_donorgiftaccesslink",
    "schools_grantmilestone",
    "schools_grantreport",
]

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _existing(cursor, tables):
    """Only touch tables that exist AND already carry ``school_id`` (see 0081)."""
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


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in _existing(cursor, TABLES):
            policy = f"rls_tenant_{table}"
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


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in _existing(cursor, TABLES):
            policy = f"rls_tenant_{table}"
            cursor.execute(f'DROP POLICY IF EXISTS {policy} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("schools", "0085_advancement_grant_child_school_column")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
