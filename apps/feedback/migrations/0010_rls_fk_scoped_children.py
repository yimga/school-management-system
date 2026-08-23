# RLS for feedback's FK-scoped child tables (PostgreSQL single-schema mode only).
#
# 0008/0009 enumerate only the eight feedback models that carry a literal school
# FK. feedback_feedbackcomment, feedback_feedbackattachment and
# feedback_feedbacktriageevent hold tenant data too -- internal (operator-only)
# triage notes, triage history, and every attachment's storage path -- but they
# reach their school through a parent FK, so they were in neither list: no
# ENABLE, no policy, no FORCE. Under USE_DJANGO_TENANTS=0 that means any tenant
# connection could `SELECT * FROM feedback_feedbackcomment` and read every
# school's rows.
#
# communication/0031 already established the FK-scoped policy shape for
# communication_threadmessageattachment; this mirrors it. Two of the three
# children hang off EITHER a FeedbackSubmission or a FeatureRequest (both FKs are
# nullable), so the USING clause accepts a match through either parent. A row
# with both parents NULL is orphaned and stays invisible outside a bypass --
# default-deny is the right direction for an unattachable row.
#
# ENABLE + CREATE POLICY + FORCE all happen here, as in schoolops/0040: this
# migration lands after both global FORCE sweeps (schools/0048, schools/0083),
# so neither can cover these tables, and an un-FORCE'd policy does not apply to
# the table owner -- which is the role Django runs as in RLS mode.
#
# No-op on SQLite and under USE_DJANGO_TENANTS=True (schema-per-tenant, where
# search_path is the boundary and RLS is unused).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

POLICY_PREFIX = "feedback_tenant"

# {table: [(parent_table, fk_column), ...]} — the row belongs to the active
# school when ANY of its (nullable) parents does.
FK_SCOPED_TABLES = {
    "feedback_feedbackcomment": [
        ("feedback_feedbacksubmission", "feedback_id"),
        ("feedback_featurerequest", "feature_request_id"),
    ],
    "feedback_feedbackattachment": [
        ("feedback_feedbacksubmission", "feedback_id"),
    ],
    "feedback_feedbacktriageevent": [
        ("feedback_feedbacksubmission", "feedback_id"),
        ("feedback_featurerequest", "feature_request_id"),
    ],
}


def _using_clause(table, parents):
    exists = "\n    OR ".join(
        f"""EXISTS (
        SELECT 1 FROM {parent} p{index}
        WHERE p{index}.id = {table}.{fk}
          AND current_setting('app.current_school_id', true) IS NOT NULL
          AND p{index}.school_id::text = current_setting('app.current_school_id', true)
    )"""
        for index, (parent, fk) in enumerate(parents)
    )
    return f"""(
    current_setting('app.rls_bypass', true) = 'on'
    OR {exists}
)"""


def _existing(cursor, tables):
    # Mirrors communication/0031: a table absent from this schema is skipped
    # rather than aborting the whole migration.
    cursor.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname = current_schema()
          AND c.relname = ANY(%s)
        """,
        [list(tables)],
    )
    return {row[0] for row in cursor.fetchall()}


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        present = _existing(cursor, list(FK_SCOPED_TABLES))
        for table, parents in FK_SCOPED_TABLES.items():
            if table not in present:
                continue
            suffix = table.replace("feedback_", "", 1)
            policy_name = f"{POLICY_PREFIX}_{suffix}"
            using = _using_clause(table, parents)
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {using}
                WITH CHECK {using};
                """
            )
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        present = _existing(cursor, list(FK_SCOPED_TABLES))
        for table in FK_SCOPED_TABLES:
            if table not in present:
                continue
            suffix = table.replace("feedback_", "", 1)
            cursor.execute(
                f"DROP POLICY IF EXISTS {POLICY_PREFIX}_{suffix} ON {table};"
            )
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0009_rls_policy_default_deny"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
