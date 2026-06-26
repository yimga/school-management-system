# RLS for tenant-scoped schoolops tables. PostgreSQL only; no-op for SQLite/schema-per-tenant.

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


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SCHOOLOPS_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            short = table.replace("schoolops_", "")
            cursor.execute(
                f"""
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
                """
            )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SCHOOLOPS_TABLES:
            short = table.replace("schoolops_", "")
            cursor.execute(f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{short} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("schoolops", "0029_resource_booking_exclude_constraint"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
