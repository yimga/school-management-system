# RLS for reports_reportcardbatch (PostgreSQL, single-schema RLS mode only).
#
# reports.ReportCardBatch (created in 0026, tenant-scoped via a `school` FK) shipped
# with NO row-level-security policy. Its creating migration depends on
# schools/0083_force_rls_late_enabled_tables, so it runs AFTER both global FORCE
# sweeps (0048, 0083) and the 0081 backfill -- none of which can cover it. This is
# the same defense-in-depth gap the W24 immunization tables had (fixed in
# schoolops/0038); a permanent seal (apps/schools/tests/test_rls_tenant_table_coverage.py)
# now catches this class, and it flagged this table.
#
# ENABLE + CREATE POLICY + FORCE in one pass, so the table is fully protected
# without depending on any future sweep. No-op on SQLite and under
# USE_DJANGO_TENANTS=True (schema-per-tenant, where search_path is the boundary).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "reports_reportcardbatch"
POLICY_NAME = "reports_tenant_reportcardbatch"

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )
        cursor.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {TABLE};")
        cursor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0026_reportcardbatch"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
