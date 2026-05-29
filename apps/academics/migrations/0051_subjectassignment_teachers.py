"""v4.00.42 — SubjectAssignment.teachers M2M for OneRoster teacher enrollments.

Backs ``apps.api.oneroster_csv_importer._apply_enrollments`` flip from
``teacher_accepted_deferred`` to real writes: a OneRoster enrollment row
with ``role=teacher`` adds the resolved User to every SubjectAssignment
under the resolved Classroom for the active term/year.

Pure AddField — no backfill required (empty by default).
"""

from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0050_certification_candidate_continuous_assessment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="subjectassignment",
            name="teachers",
            field=models.ManyToManyField(
                blank=True,
                help_text="Users (with TeacherProfile) responsible for teaching this assignment slot.",
                related_name="taught_subject_assignments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
