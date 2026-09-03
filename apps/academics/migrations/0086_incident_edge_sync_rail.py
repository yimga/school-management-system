"""Edge-sync rail contract for Incident (behavior domain, 2026-09-03).

Measured: the behavior domain's imports were STRANDED -- an incident recorded or
imported on a box never reached the cloud, silently. Incident rides two-way and
is insertable across the rail (offline discipline logging is a primary use), so
it takes the standard anchor + cursor columns.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0085_classroom_specialty_code_per_school_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="incident",
            name="client_offline_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddConstraint(
            model_name="incident",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id", ""), _negated=True),
                fields=("school", "client_offline_id"),
                name="uniq_incident_school_offline_id",
            ),
        ),
    ]
