"""
Seed business glossary with education terms (Path-to-10 — full glossary).

Run: python manage.py seed_business_glossary [--dry-run]
Creates BusinessGlossaryEntry for common education terminology so metadata catalog
and lineage can map business terms to entity/field codes. Non-negotiable for 10/10.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.metadata.models import BusinessGlossaryEntry

# (term, definition, entity_code, field_name, locale)
GLOSSARY_ENTRIES = [
    (
        "Class",
        "Instructional group; may be called form, homeroom, or year group depending on region.",
        "classroom",
        "",
        "en",
    ),
    ("Form", "UK/Commonwealth term for class or year group.", "classroom", "", "en"),
    (
        "Homeroom",
        "Primary class or advisory group for a student.",
        "classroom",
        "",
        "en",
    ),
    (
        "Year group",
        "Students in the same grade/year level.",
        "student",
        "grade_level",
        "en",
    ),
    (
        "Cohort",
        "Group of students progressing together (e.g. by intake year).",
        "student",
        "",
        "en",
    ),
    ("Term", "Academic period (e.g. semester, trimester, quarter).", "", "", "en"),
    ("Trimester", "One of three academic terms in a year.", "", "", "en"),
    ("Semester", "One of two main academic terms.", "", "", "en"),
    ("Levy", "Fee or charge (often used in AU/NZ).", "invoice", "amount", "en"),
    (
        "Tuition",
        "Instruction fee; may map to invoice or fee plan.",
        "invoice",
        "amount",
        "en",
    ),
    (
        "Fee",
        "Charge for a good or service (e.g. activity fee, lab fee).",
        "invoice",
        "amount",
        "en",
    ),
    ("Invoice", "Bill for fees/tuition sent to family.", "invoice", "", "en"),
    (
        "Guardian",
        "Person with legal responsibility for a student.",
        "parent_guardian",
        "",
        "en",
    ),
    ("Parent", "Parent or guardian linked to a student.", "parent_guardian", "", "en"),
    (
        "Sponsor",
        "Person or organization responsible for payment (e.g. company, embassy).",
        "person",
        "",
        "en",
    ),
    ("Report card", "Summary of grades and attendance for a term.", "", "", "en"),
    ("Transcript", "Official record of courses and grades.", "grade", "", "en"),
    (
        "Admission number",
        "Unique identifier for a student at a school.",
        "student",
        "admission_number",
        "en",
    ),
    ("Attendance", "Record of presence/absence for a session.", "attendance", "", "en"),
    ("Grade", "Assessment result or mark.", "grade", "grade_value", "en"),
    ("Assessment", "Test, exam, or assignment used for grading.", "grade", "", "en"),
    ("Application", "Admission or enrollment application.", "application", "", "en"),
    ("Applicant", "Person who has applied for admission.", "application", "", "en"),
]


class Command(BaseCommand):
    help = "Seed BusinessGlossaryEntry with education terms (Path-to-10)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Do not write to DB."
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")
        created = 0
        with transaction.atomic():
            for term, definition, entity_code, field_name, locale in GLOSSARY_ENTRIES:
                _, was_created = BusinessGlossaryEntry.objects.get_or_create(
                    term=term,
                    locale=locale,
                    defaults={
                        "definition": definition,
                        "entity_code": entity_code or "",
                        "field_name": field_name or "",
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(
                    f"Would create up to {len(GLOSSARY_ENTRIES)} entries ({created} new)."
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Business glossary: {created} new entries; {len(GLOSSARY_ENTRIES)} total defined."
                    )
                )
