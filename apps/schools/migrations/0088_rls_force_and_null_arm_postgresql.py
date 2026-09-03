"""Force-bind row-level security for schools (198-table burndown, 2026-09-03).

PostgreSQL exempts a table's OWNER from its own policies unless the table is force-bound (ALTER TABLE ... FORCE), and Django connects as the owner -- so on an RLS box
(single schema, USE_DJANGO_TENANTS=0) an un-FORCEd policy is decorative on
the only connection that matters. No-op under schema-per-tenant and on
SQLite (should_apply_rls).

TABLES also get their policy REPLACED with the canonical
null-arm form (metadata/0012, people/0076 shape): their school FK is
NULLABLE and the old clause had no `school_id IS NULL` arm, so the
moment FORCE binds, every platform-scope row (school IS NULL) would
become invisible to all sessions and INSERTs of such rows would fail
42501. NULL here is the platform/pre-tenant scope (definitions,
platform runs, keys, logs), the same reviewed outcome as the repo's
canonical shapes. Reversing drops the canonical policy WITHOUT
resurrecting the old armless one -- the table stays enabled and
default-deny, which fails closed.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES_FORCE = [
    "schools_schoolmembership",
]

TABLES = [
    "schools_marketingfunnelevent",
    "schools_tenantinvite",
]

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR school_id IS NULL
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES_FORCE:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            cursor.execute(
                "DO $$ DECLARE pol record; BEGIN "
                "FOR pol IN SELECT policyname FROM pg_policies "
                "WHERE schemaname = current_schema() AND tablename = '" + table + "' LOOP "
                "EXECUTE format('DROP POLICY %I ON " + table + "', pol.policyname); "
                "END LOOP; END $$;"
            )
            policy_name = _policy_name(table)
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def _policy_name(table):
    prefix = "schools_"
    suffix = table[len(prefix):] if table.startswith(prefix) else table
    return f"schools_rls_{suffix}"


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"DROP POLICY IF EXISTS {_policy_name(table)} ON {table};")
        for table in TABLES_FORCE:
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):

    dependencies = [("schools", "0087_alter_school_subdomain")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
