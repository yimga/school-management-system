# Pass 9.C: SLA tracking columns on ExportJob + EraseRequest.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0013_ferpa_disclosure"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportjob",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="exportjob",
            name="sla_breach_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eraserequest",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eraserequest",
            name="sla_breach_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
