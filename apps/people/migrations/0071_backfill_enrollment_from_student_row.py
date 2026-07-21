"""Backfill one Enrollment per existing student from the student row (item 2.2).

Live tenants have data. This migration must give every existing student the
academic history the new table represents WITHOUT re-classing or re-grading
anybody: it only ever READS ``StudentProfile.academic_year``/``classroom`` and
writes a new row. No student field is touched, so a tenant's current class
assignments, report cards and rankings are bit-identical afterwards.

Shape of the backfilled row:

* a student who is still ``is_active`` gets an **ACTIVE** enrollment — the one
  the new ``current_classroom`` derivation resolves through, so nothing changes
  for readers that were using the raw field;
* a student who has already left gets a **closed** enrollment carrying the
  outcome their ``status`` already implies (ALUMNI -> GRADUATED, TRANSFERRED ->
  TRANSFERRED_OUT, otherwise WITHDRAWN). Opening an ACTIVE row for an alumnus
  would both be false and collide with the one-active-per-student constraint.

Students with no ``academic_year`` are skipped: there is no year to anchor an
enrollment to, and inventing one would be fabricating history.

Idempotent — a student who already has any enrollment is left alone, so a
re-run (or a tenant provisioned after this shipped) cannot double up.

Reverse is a deliberate no-op: this cannot distinguish a backfilled row from one
a school has since edited, and deleting real academic history to undo a
migration is never the right trade.
"""

from django.db import migrations

BATCH = 500


def backfill(apps, schema_editor):
    StudentProfile = apps.get_model("people", "StudentProfile")
    Enrollment = apps.get_model("people", "Enrollment")

    already = set(Enrollment.objects.values_list("student_id", flat=True))

    students = (
        StudentProfile.objects.filter(academic_year__isnull=False)
        .exclude(pk__in=already)
        .select_related("academic_year")
        .order_by("pk")
    )

    pending = []
    for student in students.iterator(chunk_size=BATCH):
        year = student.academic_year
        if student.is_active:
            status = "ACTIVE"
            outcome = ""
            exit_date = None
        else:
            status = "COMPLETED"
            if student.status == "ALUMNI":
                outcome = "GRADUATED"
            elif student.status == "TRANSFERRED":
                outcome = "TRANSFERRED_OUT"
                status = "WITHDRAWN"
            else:
                outcome = "WITHDRAWN"
                status = "WITHDRAWN"
            exit_date = getattr(year, "end_date", None)
        pending.append(
            Enrollment(
                school_id=student.school_id,
                student_id=student.pk,
                academic_year_id=student.academic_year_id,
                classroom_id=student.classroom_id,
                specialty_id=student.specialty_id,
                section=student.section or "",
                status=status,
                entry_date=student.joined_date or getattr(year, "start_date", None),
                exit_date=exit_date,
                outcome=outcome,
                outcome_reason=(
                    "Backfilled from the student record when enrollments became "
                    "first-class."
                    if outcome
                    else ""
                ),
            )
        )
        if len(pending) >= BATCH:
            Enrollment.objects.bulk_create(pending, batch_size=BATCH)
            pending = []
    if pending:
        Enrollment.objects.bulk_create(pending, batch_size=BATCH)


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0070_enrollment_rls_postgresql"),
    ]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
