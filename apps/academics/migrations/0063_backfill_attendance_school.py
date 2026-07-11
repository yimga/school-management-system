"""Backfill Attendance.school for legacy rows created NULL by the teacher
roll-call web UI / mobile sync / REST `record` paths (which omitted school before
the model-level chokepoint was added). A NULL-school row escapes every
school-scoped consumer AND the offboarding purge (orphan student PII). This heals
existing rows from their student's school in one correlated-subquery UPDATE.
"""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_attendance_school(apps, schema_editor):
    Attendance = apps.get_model("academics", "Attendance")
    StudentProfile = apps.get_model("people", "StudentProfile")
    student_school = StudentProfile.objects.filter(pk=OuterRef("student_id")).values(
        "school_id"
    )[:1]
    (
        Attendance.objects.filter(school__isnull=True)
        .exclude(student__school__isnull=True)
        .update(school_id=Subquery(student_school))
    )


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0062_room_bookable_resource"),
        # Latest people migration so the historical StudentProfile carries school_id.
        ("people", "0066_transfercase_batch_status_index"),
    ]

    operations = [
        migrations.RunPython(
            backfill_attendance_school, migrations.RunPython.noop
        ),
    ]
