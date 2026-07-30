# Default-deny RLS for tenant-scoped communication tables (extends 0014's list).
# PostgreSQL single-schema mode only (should_apply_rls); no-op under
# schema-per-tenant and SQLite.
#
# 22 of these tables carry a `school_id` column and get the standard bypass-aware
# school_id policy. communication_threadmessageattachment has NO school_id of its
# own -- it is FK-scoped to communication_threadmessage via message_id -- so it
# gets a policy that resolves the tenant through its parent thread message.
#
# The pre-fix version built a school_id policy for ALL 23 tables unconditionally,
# so on a fresh single-schema Postgres `migrate` aborted with
# `column "school_id" does not exist` the moment it reached the attachment table
# -- meaning the default-deny policies for the whole extend-list were never
# actually created. SQLite hid it (no-op there); and the tenants-rls Postgres CI
# that would have caught it has been unable to run. The school_id lookup is now
# guarded (mirrors schools/0081) so a table missing the column is skipped, not a
# crash.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

# Tenant tables that carry their own school_id column.
SCHOOL_ID_TABLES = [
    "communication_alertrule",
    "communication_announcement",
    "communication_announcementauditlog",
    "communication_classannouncement",
    "communication_contactrequest",
    "communication_contactrequestattachment",
    "communication_directconversation",
    "communication_message",
    "communication_messagethread",
    "communication_threadmessage",
    "communication_threadreadstate",
    "communication_achievementevent",
    "communication_narrativefeedback",
    "communication_feeditem",
    "communication_outboundmessagequeue",
    "communication_communicationtemplate",
    "communication_smssendlog",
    "communication_consent_event",
    "communication_message_delivery_receipt",
    "communication_messageblock",
    "communication_threadmessagemention",
    "communication_threadmute",
]
# FK-scoped tables (no school_id of their own): {table: (parent_table, fk_column)}.
# Isolated through the parent row's school_id.
FK_SCOPED_TABLES = {
    "communication_threadmessageattachment": (
        "communication_threadmessage",
        "message_id",
    ),
}

SCHOOL_ID_USING = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _fk_using(table, parent, fk):
    # Bypass, else the row's parent must belong to the active school.
    return f"""(
    current_setting('app.rls_bypass', true) = 'on'
    OR EXISTS (
        SELECT 1 FROM {parent} ptm
        WHERE ptm.id = {table}.{fk}
          AND current_setting('app.current_school_id', true) IS NOT NULL
          AND ptm.school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _existing_with_school_id(cursor, tables):
    cursor.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND n.nspname = current_schema()
          AND c.relname = ANY(%s)
          AND a.attname = 'school_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        [list(tables)],
    )
    return {row[0] for row in cursor.fetchall()}


def _existing(cursor, tables):
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


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        present = _existing_with_school_id(cursor, SCHOOL_ID_TABLES)
        for table in SCHOOL_ID_TABLES:
            if table not in present:
                continue
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {SCHOOL_ID_USING}
                WITH CHECK {SCHOOL_ID_USING};
                """
            )
        present_fk = _existing(cursor, list(FK_SCOPED_TABLES))
        for table, (parent, fk) in FK_SCOPED_TABLES.items():
            if table not in present_fk:
                continue
            policy_name = f"{table}_tenant_isolation"
            using = _fk_using(table, parent, fk)
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {using}
                WITH CHECK {using};
                """
            )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    all_tables = list(SCHOOL_ID_TABLES) + list(FK_SCOPED_TABLES)
    with connection.cursor() as cursor:
        present = _existing(cursor, all_tables)
        for table in all_tables:
            if table not in present:
                continue
            cursor.execute(
                f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0030_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
