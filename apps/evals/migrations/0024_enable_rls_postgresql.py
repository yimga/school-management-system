# RLS (Row-Level Security) for tenant-scoped tables. PostgreSQL only; no-op for SQLite/MySQL.

from django.db import migrations, connection

EVALS_TABLES = ["evals_assessmentweights", "evals_teacherassignment", "evals_evaluation"]
POLICY_PREFIX = "evals_tenant"


def enable_rls(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        for table in EVALS_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            short = table.replace("evals_", "")
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
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        for table in EVALS_TABLES:
            short = table.replace("evals_", "")
            cursor.execute(f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{short} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("evals", "0023_add_school_fk"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
