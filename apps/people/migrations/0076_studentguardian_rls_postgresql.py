"""RLS for ``people_studentguardian`` -- tenant-scoped by 0075, enumerated here.

Every ``*_enable_rls_postgresql.py`` in this tree hard-codes a literal TABLES list
frozen at authoring time, so a model given a ``school`` FK AFTER its app's RLS
migration was written joins the uncovered set silently -- exactly what
``scripts/scan_rls_table_coverage.py`` exists to catch, and exactly what it caught
when 0075 added ``school`` to this table. ``people/0026`` enumerates only
``people_teacherprofile`` and ``people_studentprofile``; this table needs its own
enumeration.

It matters more than a link table's size suggests: the row IS the access grant.
Whoever can read it learns which adult is attached to which child, and whoever can
write it can attach an adult to a child -- ``can_view_finance`` and
``can_view_results`` hang directly off this row.

Policy body is the default-deny + bypass form from ``people/0074``, with FORCE,
plus one deliberate difference: the ``school_id IS NULL`` arm leads the tenant
comparison. ``school`` here is NULLABLE because ``StudentProfile.school`` is
nullable -- a legacy schoolless student's link derives ``school=None`` through
``StudentGuardian.save()`` -- and without the arm those platform-scope rows would
be invisible to every session (``NULL::text = '<id>'`` is NULL, so USING is
false). See ``scripts/scan_rls_null_school_arm.py``.

No-op under schema-per-tenant (``USE_DJANGO_TENANTS=1``), where isolation comes
from the schema instead -- see ``apps/schools/rls.py::should_apply_rls``.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ["people_studentguardian"]

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

    dependencies = [("people", "0075_student_guardian_edge_sync_rail")]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
