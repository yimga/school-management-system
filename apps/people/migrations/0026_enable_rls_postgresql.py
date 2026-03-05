# RLS (Row-Level Security) for tenant-scoped tables. PostgreSQL only; no-op for SQLite/MySQL or schema-per-tenant.

from django.db import migrations, connection

from apps.schools.rls import should_apply_rls

PEOPLE_TABLES = ["people_teacherprofile", "people_studentprofile"]


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in PEOPLE_TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"""
                CREATE POLICY {policy_name} ON {table}
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
        for table in PEOPLE_TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0025_add_custom_attributes"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
