"""Backfill ``Evaluation.school`` for rows written before the save() chokepoint.

``Evaluation.save()`` now derives the tenant FK the same way
``_resolve_grading_school()`` does, but every row already on disk was written by
a path that omitted it (marks grid, OCR apply, offline sync, both CSV
importers). Those rows stay invisible to ``views_drilldown`` and the Platform v1
API — both filter ``school=request.school`` — until the column is filled, so
heal them here in the resolver's own priority order.

Pure data (no model-state change), and re-runnable: each pass touches only rows
that are still NULL. Reversal is a no-op — we cannot tell a backfilled row from
one that always carried its school, and un-setting it would re-open the hole.
"""

from django.db import migrations, models


# Same precedence as apps/evals/models.py::Evaluation._resolve_grading_school:
# the assignment first, then the student, then the calendar objects, and the
# assignment's classroom last (classroom hangs off the assignment, not the row).
_SOURCES = (
    ("subject_assignment_id", "academics", "SubjectAssignment", "school_id"),
    ("student_id", "people", "StudentProfile", "school_id"),
    ("academic_year_id", "academics", "AcademicYear", "school_id"),
    ("term_id", "academics", "Term", "school_id"),
)


def _backfill(apps, schema_editor):
    Evaluation = apps.get_model("evals", "Evaluation")

    for fk_name, app_label, model_name, source_field in _SOURCES:
        Source = apps.get_model(app_label, model_name)
        Evaluation.objects.filter(school_id=None).exclude(
            **{fk_name: None}
        ).update(
            school_id=models.Subquery(
                Source.objects.filter(
                    pk=models.OuterRef(fk_name)
                ).values(source_field)[:1]
            )
        )

    # Classroom hangs off the assignment, not off the row, so reach it with a
    # join INSIDE the subquery rather than a second correlated level.
    SubjectAssignment = apps.get_model("academics", "SubjectAssignment")
    Evaluation.objects.filter(school_id=None).exclude(
        subject_assignment_id=None
    ).update(
        school_id=models.Subquery(
            SubjectAssignment.objects.filter(
                pk=models.OuterRef("subject_assignment_id")
            ).values("classroom__school_id")[:1]
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ("evals", "0039_edge_sync_anchor_evaluation"),
        ("academics", "0001_initial"),
        ("people", "0001_initial"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
