"""
Plan II: Report-card CSV export.
Exports term grades (Evaluations) for an academic year and term to CSV.
Usage: python manage.py export_report_cards_csv --year=2025/2026 --term=1 [--school=UUID] [--classroom=ID] [--output=out.csv]
"""
from __future__ import annotations

import csv
import io
from django.core.management.base import BaseCommand

from apps.academics.models import AcademicYear, Term
from apps.evals.models import Evaluation


def export_term_grades_csv(
    academic_year: AcademicYear,
    term: Term,
    *,
    school_id=None,
    classroom_id=None,
) -> str:
    """Build CSV content: student_code, first_name, last_name, classroom, subject, seq1, seq2, exam, total_score."""
    qs = (
        Evaluation.objects.filter(
            academic_year=academic_year,
            term=term,
        )
        .select_related(
            "student",
            "student__classroom",
            "subject_assignment__subject",
            "subject_assignment__classroom",
        )
    )
    if school_id:
        qs = qs.filter(school_id=school_id)
    if classroom_id:
        qs = qs.filter(subject_assignment__classroom_id=classroom_id)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "student_code",
        "first_name",
        "last_name",
        "classroom",
        "subject",
        "seq1_score",
        "seq2_score",
        "exam_score",
        "total_score",
        "remarks",
    ])
    for ev in qs.order_by("student__student_code", "subject_assignment__subject__name"):
        student = ev.student
        subj = ev.subject_assignment.subject if ev.subject_assignment else None
        classroom_name = (student.classroom.name if student.classroom else "") or ""
        writer.writerow([
            (student.student_code or ""),
            (student.first_name or ""),
            (student.last_name or ""),
            classroom_name,
            (subj.name if subj else ""),
            str(ev.seq1_score) if ev.seq1_score is not None else "",
            str(ev.seq2_score) if ev.seq2_score is not None else "",
            str(ev.exam_score) if ev.exam_score is not None else "",
            str(ev.total_score) if getattr(ev, "total_score", None) is not None else "",
            (ev.remarks or "")[:200],
        ])
    return out.getvalue()


class Command(BaseCommand):
    help = "Plan II: Export term report-card data (grades) to CSV."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=str, required=True, help="Academic year name (e.g. 2025/2026)")
        parser.add_argument(
            "--term",
            type=str,
            required=True,
            help="Term name or position (e.g. 1 or Term 1)",
        )
        parser.add_argument("--school", type=str, default=None, help="Optional: school UUID")
        parser.add_argument("--classroom", type=int, default=None, help="Optional: classroom ID")
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output file path; if omitted, prints to stdout",
        )

    def handle(self, *args, **options):
        year_name = (options["year"] or "").strip()
        term_arg = (options["term"] or "").strip()
        school_id = options.get("school")
        classroom_id = options.get("classroom")
        output_path = options.get("output")

        year = AcademicYear.objects.filter(name=year_name).first()
        if not year:
            self.stderr.write(self.style.ERROR(f"Academic year not found: {year_name}"))
            return
        term = Term.objects.filter(academic_year=year, name=term_arg).first()
        if not term:
            try:
                pos = int(term_arg)
                term = Term.objects.filter(academic_year=year, position=pos).first()
            except ValueError:
                pass
        if not term:
            self.stderr.write(self.style.ERROR(f"Term not found: {term_arg}"))
            return

        content = export_term_grades_csv(
            year,
            term,
            school_id=school_id,
            classroom_id=classroom_id,
        )
        if output_path:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                f.write(content)
            self.stdout.write(self.style.SUCCESS(f"Wrote {output_path}"))
        else:
            self.stdout.write(content)
