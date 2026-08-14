# RLS for the W24 immunization tables (PostgreSQL, single-schema RLS mode only).
#
# schools_immunizationrecord + schools_vaccinerequirement (created in 0037) are
# tenant-scoped via a `school` FK but shipped with NO row-level-security policy.
# Their creating migration (0037) depends on schools/0083_force_rls_late_enabled_tables,
# so it runs AFTER both global FORCE sweeps (0048, 0083) -- meaning neither sweep
# can cover them, and a plain ENABLE+POLICY (as schoolops/0033 did for
# inventorymovement, relying on the later 0083 sweep to FORCE it) would leave these
# two tables enabled+policied but UN-FORCE'd: their tenant policy would bind "for
# everyone except the owner -- i.e. for nobody", so the Postgres table owner (the
# role Django runs as in RLS mode) would read every school's rows.
#
# This migration therefore does all three -- ENABLE + CREATE POLICY + FORCE -- in
# one pass for each table, so they are fully protected without depending on any
# future sweep. No-op on SQLite and under USE_DJANGO_TENANTS=True (schema-per-tenant,
# where `search_path` is the boundary and RLS is unused).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

POLICY_PREFIX = "schoolops_tenant"

# (table, policy-suffix) for every W24 tenant table.
_TABLES = (
    ("schools_immunizationrecord", "immunizationrecord"),
    ("schools_vaccinerequirement", "vaccinerequirement"),
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
            # FORCE so the policy also binds for the table owner (0083 already ran
            # before these tables existed and will not re-sweep them).
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
        ("schoolops", "0037_immunizationrecord_vaccinerequirement"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
