# RLS for the M33 procurement tables (PostgreSQL, single-schema RLS mode only).
#
# These five tables are created in 0039, which lands long after BOTH global FORCE
# sweeps (schools/0048 and schools/0083). Neither sweep can therefore cover them, and
# a plain ENABLE + CREATE POLICY -- the shape schoolops/0033 used for
# inventorymovement while relying on the later 0083 sweep to FORCE it -- would leave
# them enabled and policied but UN-FORCE'd. An un-FORCE'd policy binds "for everyone
# except the table owner", and the table owner is the role Django runs as in RLS
# mode, so every school would read every other school's vendors, prices and orders.
#
# This migration therefore does all three -- ENABLE + CREATE POLICY + FORCE -- in one
# pass per table, exactly as 0038 does for the W24 immunization tables.
#
# Every one of the five carries its own school_id, including purchaseorderline and
# vendorproduct which could have reached their school through a parent FK: the policy
# below is a per-table column check, so a table without school_id cannot be protected.
#
# No-op on SQLite and under USE_DJANGO_TENANTS=True (schema-per-tenant, where
# search_path is the boundary and RLS is unused).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

POLICY_PREFIX = "schoolops_tenant"

_TABLES = (
    ("schoolops_vendor", "vendor"),
    ("schoolops_vendorproduct", "vendorproduct"),
    ("schoolops_supplyrequirement", "supplyrequirement"),
    ("schoolops_purchaseorder", "purchaseorder"),
    ("schoolops_purchaseorderline", "purchaseorderline"),
)

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table, suffix in _TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(
                f"""
                CREATE POLICY {POLICY_PREFIX}_{suffix} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table, suffix in _TABLES:
            cursor.execute(
                f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{suffix} ON {table};"
            )
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("schoolops", "0039_procurement"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
