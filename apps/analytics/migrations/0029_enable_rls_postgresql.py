# RLS enable for tenant-scoped analytics tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = ['analytics_atriskinferencerun', 'analytics_atriskoutcomelabel', 'analytics_atriskshadowrun', 'analytics_governedsavedreport', 'analytics_gradeprediction', 'analytics_gradepredictionlabel', 'analytics_gradepredictionshadowrun', 'analytics_interventionlog', 'analytics_riskdigestrecipient', 'analytics_riskfactor', 'analytics_riskthresholds', 'analytics_studentatrisksignal', 'analytics_studentsignals']


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
        ("analytics", "0028_rename_analytics_a_school__1f5b2a_idx_analytics_a_school__1a48fe_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
