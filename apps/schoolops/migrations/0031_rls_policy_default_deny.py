# RLS default-deny: allow only when app.current_school_id matches or app.rls_bypass=on.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

SCHOOLOPS_TABLES = [
    "schoolops_campus",
    "schoolops_inventoryitem",
    "schoolops_route",
    "schoolops_bus",
    "schoolops_busboardingevent",
    "schoolops_hostel",
    "schoolops_hostelroom",
    "schoolops_canteenmeal",
    "schoolops_healthrecord",
    "schoolops_biometricdevice",
    "schoolops_biometricattendancelog",
    "schoolops_libraryitem",
    "schoolops_libraryloan",
    "schoolops_substitutecover",
    "schoolops_visitorcheckin",
    "schoolops_maintenancerequest",
    "schoolops_possaleline",
    "schoolops_transportassignment",
    "schoolops_hostelassignment",
    "schoolops_mealplanbalance",
    "schoolops_bookableresource",
    "schoolops_resourcebooking",
]
POLICY_PREFIX = "schoolops_tenant"
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
        for table in SCHOOLOPS_TABLES:
            short = table.replace("schoolops_", "")
            policy_name = f"{POLICY_PREFIX}_{short}"
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
        for table in SCHOOLOPS_TABLES:
            short = table.replace("schoolops_", "")
            policy_name = f"{POLICY_PREFIX}_{short}"
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
    dependencies = [
        ("schoolops", "0030_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny_policy, reverse_default_deny_policy),
    ]
