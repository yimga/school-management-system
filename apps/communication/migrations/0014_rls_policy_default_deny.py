# RLS default-deny policy: allow only when app.current_school_id matches or app.rls_bypass=on.
# Run only in single-schema (RLS) mode; no-op when USE_DJANGO_TENANTS=True.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

COMMUNICATION_TABLES = [
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
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_default_deny_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
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
                """
            )


class Migration(migrations.Migration):
    dependencies = [("communication", "0013_virtualclassroom_default_jitsi")]
    operations = [
        migrations.RunPython(apply_default_deny_policy, reverse_default_deny_policy)
    ]
