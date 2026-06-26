# RLS enable for tenant-scoped social media tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

SOCIAL_MEDIA_TABLES = [
    "social_media_socialmediaintegration",
    "social_media_socialpostoutbox",
    "social_media_socialmoderationitem",
    "social_media_socialcampaignattribution",
]


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SOCIAL_MEDIA_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in SOCIAL_MEDIA_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0001_social_media_integration"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
