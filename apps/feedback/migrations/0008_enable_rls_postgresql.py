# RLS enable for tenant-scoped feedback tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['feedback_featurerequest', 'feedback_feedbacksubmission', 'feedback_feedbackvote', 'feedback_helpsearchquerylog', 'feedback_supportaiinteractionreview', 'feedback_supportaisessionrating', 'feedback_supportdeflectionevent', 'feedback_surveyresponse']


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0007_help_content_gap_task"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
