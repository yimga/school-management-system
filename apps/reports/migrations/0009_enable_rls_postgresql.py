# RLS (Row-Level Security) for tenant-scoped tables. PostgreSQL only; no-op for SQLite/MySQL.

from django.db import migrations, connection


def enable_rls(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE reports_reportcard ENABLE ROW LEVEL SECURITY;")
        cursor.execute("""
            CREATE POLICY reports_reportcard_tenant_isolation ON reports_reportcard
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
        cursor.execute("DROP POLICY IF EXISTS reports_reportcard_tenant_isolation ON reports_reportcard;")
        cursor.execute("ALTER TABLE reports_reportcard DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0008_add_school_fk"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
