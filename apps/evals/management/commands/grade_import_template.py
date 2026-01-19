import csv
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Output a CSV header/template for grade imports.

    Usage:
        python manage.py grade_import_template > grade_import_template.csv
    """

    help = "Prints a CSV header/template for grade imports."

    def handle(self, *args, **options):
        fieldnames = [
            "student_code",
            "subject_assignment_id",
            "term_id",
            "teacher_username",
            "seq1",
            "seq2",
            "exam",
            "mock",
            "practical",
            "test1",
            "test2",
            "remarks",
        ]
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({})  # blank example row
        self.stdout.write(self.style.SUCCESS("CSV template written to stdout."))
