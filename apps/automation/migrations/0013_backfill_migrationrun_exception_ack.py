# §0.1.5 — backfill open exception queue for historical PARTIAL/FAILED runs

from django.db import migrations
from django.db.models import Q


def forwards(apps, schema_editor):
    MigrationRun = apps.get_model("automation", "MigrationRun")
    MigrationRun.objects.filter(exception_ack_status="NA").filter(
        Q(error_count__gt=0) | Q(status__in=("PARTIAL", "FAILED"))
    ).update(exception_ack_status="OPEN")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0012_migrationrun_exception_ack_queue"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
