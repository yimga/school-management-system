# RLS default-deny policy: allow only when app.current_school_id matches or app.rls_bypass=on.
# Run only in single-schema (RLS) mode; no-op when USE_DJANGO_TENANTS=True.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

PEOPLE_TABLES = ["people_teacherprofile", "people_studentprofile"]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in PEOPLE_TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_default_deny_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in PEOPLE_TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
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
                """
            )


class Migration(migrations.Migration):
    dependencies = [("people", "0037_audit_triggers_tenant_schema")]
    operations = [migrations.RunPython(apply_default_deny_policy, reverse_default_deny_policy)]
