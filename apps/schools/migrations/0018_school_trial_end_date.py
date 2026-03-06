# Plan X: Trial state — trial_end_date on School. Idempotent for tenant migrations.

from django.db import migrations, models


def add_trial_end_date_if_missing(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE schools_school ADD COLUMN trial_end_date date NULL;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
        else:
            cursor.execute("PRAGMA table_info(schools_school)")
            if "trial_end_date" not in [row[1] for row in cursor.fetchall()]:
                cursor.execute("ALTER TABLE schools_school ADD COLUMN trial_end_date date NULL")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0017_add_hierarchy_campus_quota_usage"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="school",
                    name="trial_end_date",
                    field=models.DateField(
                        null=True,
                        blank=True,
                        help_text="When billing_type is FREE_TRIAL, trial ends on this date.",
                    ),
                ),
            ],
            database_operations=[migrations.RunPython(add_trial_end_date_if_missing, noop)],
        ),
    ]
