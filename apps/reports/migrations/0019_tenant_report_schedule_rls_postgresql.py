# RLS for tenant-scoped scheduled reports (PostgreSQL single-schema mode only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "reports_tenantreportschedule"
POLICY_NAME = "reports_tenantreportschedule_tenant_isolation"
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_tenant_schedule_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {TABLE};")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY_NAME} ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def reverse_tenant_schedule_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {TABLE};")
        cursor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0018_tenant_report_schedule"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_schedule_rls, reverse_tenant_schedule_rls),
    ]
