"""RLS for ``people_admissionnumbersequence`` — the counter table added by 0073.

Every ``*_enable_rls_postgresql.py`` in this tree hard-codes a literal TABLES list frozen
at authoring time, so a tenant-scoped model added later is never enabled while the
app-level file-pairing gate still reports green (see the docstring of
``scripts/scan_rls_table_coverage.py``). ``people/0026`` enumerates only
``people_teacherprofile`` and ``people_studentprofile`` and ``people/0070`` only
``people_enrollment``, so this table needs its own enumeration or it joins the uncovered
set — which is exactly what happened to the sync_engine pairing tables on 2026-08-21.

It matters more here than the table's size suggests. The row IS the school's number line:
whoever can read it learns how many students a school enrolled this year, and whoever can
write it can make one school's counter hand out another school's numbers.

Policy body is the default-deny form from ``people/0070``, with FORCE — a new table has no
legacy rows to be lenient about, so it starts at the stricter policy directly, and FORCE
means the table's owner is not exempt either.

No-op under schema-per-tenant (``USE_DJANGO_TENANTS=1``), where isolation comes from the
schema instead — see ``apps/schools/rls.py::should_apply_rls``.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ["people_admissionnumbersequence"]

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

    dependencies = [("people", "0073_admission_number_sequence")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
