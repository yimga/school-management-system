# RLS default-deny for tenant-scoped platform_runtime tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['platform_runtime_blueprintinstallation', 'platform_runtime_clicktrackevent', 'platform_runtime_configurationchangerequest', 'platform_runtime_healthremediationlog', 'platform_runtime_offlineaction', 'platform_runtime_operatorintent', 'platform_runtime_operatortenantassignment', 'platform_runtime_packinstallation', 'platform_runtime_remotesupportsession', 'platform_runtime_schoolonboardingprogress', 'platform_runtime_tenantheartbeat', 'platform_runtime_tenantretentionplaybookaction', 'platform_runtime_tenantretentionplaybookauditlog']
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
            short = table.replace("platform_runtime_", "", 1)
            policy_name = f"platform_runtime_tenant_{short}"
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
            short = table.replace("platform_runtime_", "", 1)
            policy_name = f"platform_runtime_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0095_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
