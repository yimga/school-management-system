# RLS enable for tenant-scoped customersuccess tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['customersuccess_admininactivityalert', 'customersuccess_forecastscenario', 'customersuccess_helpcentersource', 'customersuccess_tenanthealthscore', 'customersuccess_tenantinterventionsuggestion', 'customersuccess_tenantmaturityscore', 'customersuccess_tenantriskalert', 'customersuccess_workflowfailureevent']


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
        ("customersuccess", "0004_benchmarkcohortmetric_benchmarkcohort_is_auto_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
