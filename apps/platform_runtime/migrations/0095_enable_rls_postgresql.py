# RLS enable for tenant-scoped platform_runtime tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['platform_runtime_blueprintinstallation', 'platform_runtime_clicktrackevent', 'platform_runtime_configurationchangerequest', 'platform_runtime_healthremediationlog', 'platform_runtime_offlineaction', 'platform_runtime_operatorintent', 'platform_runtime_operatortenantassignment', 'platform_runtime_packinstallation', 'platform_runtime_remotesupportsession', 'platform_runtime_schoolonboardingprogress', 'platform_runtime_tenantheartbeat', 'platform_runtime_tenantretentionplaybookaction', 'platform_runtime_tenantretentionplaybookauditlog']


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0094_runtimedefaults_student_results_visibility"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
