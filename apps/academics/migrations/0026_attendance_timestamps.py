from django.db import migrations, models
from django.utils import timezone


def backfill_attendance_timestamps(apps, schema_editor):
    Attendance = apps.get_model("academics", "Attendance")
    now = timezone.now()
    Attendance.objects.filter(created_at__isnull=True).update(created_at=now)
    Attendance.objects.filter(updated_at__isnull=True).update(updated_at=now)


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0025_add_incident_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="attendance",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.RunPython(backfill_attendance_timestamps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="attendance",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
