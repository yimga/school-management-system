# RLS default-deny for tenant-scoped automation tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['automation_automationapprovalqueue', 'automation_automationexecutionlog', 'automation_migrationquarantinerecord', 'automation_migrationrun', 'automation_workflow']
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("automation_", "", 1)
            policy_name = f"automation_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("automation_", "", 1)
            policy_name = f"automation_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0020_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
