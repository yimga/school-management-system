"""Edge-sync rail contract for StudentGuardian (guardians domain, 2026-09-03).

Measured: the guardians domain reached the cloud NOWHERE -- a guardian link
imported or edited on a box stayed there, silently. The model had no school
column at all, so the school-scoped delta builder could never carry it. This
adds tenant ownership (backfilled from the student), the delta cursor and the
sync anchor. The entity registers INSERT-HELD: contact/preference edits
converge two-way; creating a link stays an identity decision because it names
an accounts.User and grants access to a child's records.
"""

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import OuterRef, Subquery


def backfill_school_from_student(apps, schema_editor):
    StudentGuardian = apps.get_model("people", "StudentGuardian")
    StudentProfile = apps.get_model("people", "StudentProfile")
    StudentGuardian.objects.filter(school__isnull=True).update(
        school_id=Subquery(
            StudentProfile.objects.filter(pk=OuterRef("student_id")).values(
                "school_id"
            )[:1]
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0074_admission_sequence_rls_postgresql"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentguardian",
            name="school",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="schools.school",
            ),
        ),
        migrations.AddField(
            model_name="studentguardian",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="studentguardian",
            name="client_offline_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.RunPython(
            backfill_school_from_student, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="studentguardian",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id", ""), _negated=True),
                fields=("school", "client_offline_id"),
                name="uniq_studentguardian_school_offline_id",
            ),
        ),
    ]
