# RLS default-deny for tenant-scoped social media tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

SOCIAL_MEDIA_TABLES = [
    "social_media_socialmediaintegration",
    "social_media_socialpostoutbox",
    "social_media_socialmoderationitem",
    "social_media_socialcampaignattribution",
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
        for table in SOCIAL_MEDIA_TABLES:
            policy_name = f"social_media_tenant_{table.replace('social_media_', '')}"
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
        for table in SOCIAL_MEDIA_TABLES:
            policy_name = f"social_media_tenant_{table.replace('social_media_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0002_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]
