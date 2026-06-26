# Default-deny RLS for all tenant-scoped communication tables (extends 0014 list).

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
    "communication_threadmessageattachment",
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny(apps, schema_editor):
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


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            policy_name = f"{table}_tenant_isolation"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0030_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
