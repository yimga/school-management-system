# RLS enable for all tenant-scoped communication tables (PostgreSQL only).

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
POLICY_PREFIX = "communication_tenant"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in COMMUNICATION_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("communication", "0029_messageblock_threadmessagemention_threadmute"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
