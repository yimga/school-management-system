# RLS (Row-Level Security) for tenant-scoped tables. PostgreSQL only; no-op for SQLite/MySQL or schema-per-tenant.

from django.db import migrations, connection

from apps.schools.rls import should_apply_rls

FINANCE_TABLES = ["finance_feeplan", "finance_invoice", "finance_payment"]
POLICY_PREFIX = "finance_tenant"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in FINANCE_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            short = table.replace("finance_", "")
            cursor.execute(f"""
                CREATE POLICY {POLICY_PREFIX}_{short} ON {table}
                FOR ALL
                USING (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                )
                WITH CHECK (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                );
            """)


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in FINANCE_TABLES:
            short = table.replace("finance_", "")
            cursor.execute(f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{short} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0037_add_payment_platform_fee"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
