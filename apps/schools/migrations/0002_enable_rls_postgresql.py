# RLS (Row-Level Security) for PostgreSQL. No-op for SQLite/MySQL or schema-per-tenant.

from django.db import migrations, connection

from apps.schools.rls import should_apply_rls


def enable_rls_schoolmembership(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE schools_schoolmembership ENABLE ROW LEVEL SECURITY;"
        )
        # Allow rows where school_id matches current request's school (set by middleware)
        # When app.current_school_id is set (by middleware), restrict to that school. When not set (e.g. mgmt commands), allow all.
        cursor.execute("""
            CREATE POLICY schools_schoolmembership_tenant_isolation ON schools_schoolmembership
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


def disable_rls_schoolmembership(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "DROP POLICY IF EXISTS schools_schoolmembership_tenant_isolation ON schools_schoolmembership;"
        )
        cursor.execute(
            "ALTER TABLE schools_schoolmembership DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls_schoolmembership, disable_rls_schoolmembership),
    ]
