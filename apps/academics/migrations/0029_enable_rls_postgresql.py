# RLS (Row-Level Security) for tenant-scoped tables. PostgreSQL only; no-op for SQLite/MySQL or schema-per-tenant.

from django.db import migrations, connection

from apps.schools.rls import should_apply_rls

ACADEMICS_TABLES = [
    "academics_academicyear",
    "academics_term",
    "academics_department",
    "academics_specialty",
    "academics_classroom",
    "academics_classroompromotionmapping",
    "academics_subject",
    "academics_subjectassignment",
    "academics_attendance",
    "academics_certificationexamsession",
    "academics_certificationdocumentchecklist",
    "academics_certificationexampreset",
    "academics_certificationfeetemplate",
    "academics_classbooklist",
    "academics_curriculumstandard",
]
POLICY_PREFIX = "academics_tenant"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in ACADEMICS_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            policy_name = f"{POLICY_PREFIX}_{table.replace('academics_', '')}"
            cursor.execute(f"""
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
            """)


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in ACADEMICS_TABLES:
            policy_name = f"{POLICY_PREFIX}_{table.replace('academics_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0028_add_school_fk"),
    ]
    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
