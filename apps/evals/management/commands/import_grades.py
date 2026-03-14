import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from apps.evals.models import Evaluation
from apps.academics.models import Term, SubjectAssignment
from apps.people.models import StudentProfile, TeacherProfile


class Command(BaseCommand):
    """
    Bulk-import grades from a CSV file.

    Expected columns (header row required):
    student_code,subject_assignment_id,term_id,teacher_username(optional),
    seq1,seq2,exam,mock,practical,test1,test2,remarks

    Notes:
    - Any score column may be left blank.
    - If teacher_username is blank, the first TeacherAssignment for the subject_assignment is used, else required.
    - Existing Evaluation rows for (student, subject_assignment, term) are updated; otherwise created.
    """

    help = "Import grades from CSV into Evaluation rows."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to CSV file.")
        parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB.")

    def handle(self, *args, **options):
        path = options["csv_path"]
        dry_run = options["dry_run"]

        try:
            fh = open(path, newline="", encoding="utf-8")
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        reader = csv.DictReader(fh)
        required_cols = {"student_code", "subject_assignment_id", "term_id"}
        missing = required_cols - set(reader.fieldnames or [])
        if missing:
            raise CommandError(f"Missing required columns: {', '.join(sorted(missing))}")

        created, updated = 0, 0
        for row in reader:
            try:
                student = StudentProfile.objects.get(student_code=row["student_code"])
            except StudentProfile.DoesNotExist:
                self.stderr.write(f"Skipping unknown student_code={row['student_code']}")
                continue

            try:
                sa = SubjectAssignment.objects.get(id=row["subject_assignment_id"])
            except SubjectAssignment.DoesNotExist:
                self.stderr.write(f"Skipping unknown subject_assignment_id={row['subject_assignment_id']}")
                continue

            try:
                term = Term.objects.get(id=row["term_id"])
            except Term.DoesNotExist:
                self.stderr.write(f"Skipping unknown term_id={row['term_id']}")
                continue

            teacher = None
            username = (row.get("teacher_username") or "").strip()
            if username:
                try:
                    teacher = TeacherProfile.objects.get(user__username=username)
                except TeacherProfile.DoesNotExist:
                    self.stderr.write(f"Teacher not found for username={username}; skipping row.")
                    continue
            else:
                teacher_assignment = sa.teacher_assignments.first()
                teacher = teacher_assignment.teacher if teacher_assignment else None

            if teacher is None:
                self.stderr.write(
                    f"Skipping row for student_code={student.student_code}: no teacher found or assigned."
                )
                continue

            scores = {
                "seq1_score": _to_decimal(row.get("seq1")),
                "seq2_score": _to_decimal(row.get("seq2")),
                "exam_score": _to_decimal(row.get("exam")),
                "mock_score": _to_decimal(row.get("mock")),
                "practical_score": _to_decimal(row.get("practical")),
                "test1": _to_decimal(row.get("test1")),
                "test2": _to_decimal(row.get("test2")),
                "remarks": row.get("remarks", "").strip(),
            }

            defaults = scores | {"teacher": teacher}
            if dry_run:
                continue

            obj, was_created = Evaluation.objects.update_or_create(
                academic_year=sa.academic_year,
                term=term,
                subject_assignment=sa,
                student=student,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        fh.close()
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete; no rows written."))
        self.stdout.write(self.style.SUCCESS(f"Import finished. created={created}, updated={updated}"))


def _to_decimal(value):
    if value is None:
        return None
    val = str(value).strip()
    if val == "":
        return None
    try:
        return Decimal(val)
    except (ValueError, TypeError, InvalidOperation):
        return None
