"""RLS for ``people_provisioningrequest`` -- new tenant-scoped table, enumerated here.

Every ``*_rls_postgresql.py`` in this tree hard-codes a TABLES list frozen at
authoring time, so a table added later joins the uncovered set silently. That is
what ``scripts/scan_rls_table_coverage.py`` exists to catch, and it caught this
one on the first push attempt rather than after the table shipped unprotected.

It earns the protection on content. The row carries a person's name, staff id and
phone number lifted off an offline box, and its ``status`` column is an
authorisation decision: whoever can write it can mark a request APPROVED, and the
approval screen mints a User from exactly that. A leak across tenants would hand
one school the staff roster of another; a write across tenants would hand it an
account in another school.

The ``school_id IS NULL`` arm is carried for shape, not for reach: ``school`` is
NOT NULL on this model, so the arm cannot match a row that exists today. It stays
because it is the canonical policy body used by ``people/0074``, ``0076`` and
``0077`` and checked by ``scripts/scan_rls_null_school_arm.py`` -- if the column
is ever made nullable, the table keeps working instead of silently blinding every
platform-scope row the moment FORCE binds.

FORCE is not optional. PostgreSQL exempts a table's owner from its own policies,
and Django connects as the owner, so on an RLS box an un-FORCEd policy is
decorative on the only connection that matters (see ``people/0077``).

No-op under schema-per-tenant (``USE_DJANGO_TENANTS=1``), where isolation comes
from the schema instead, and on SQLite -- see ``apps/schools/rls.py::should_apply_rls``.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ["people_provisioningrequest"]

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
        for table in TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy_name = f"people_rls_{table.replace('people_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):

    dependencies = [("people", "0078_provisioning_request")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
