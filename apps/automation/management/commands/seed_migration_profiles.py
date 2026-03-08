"""
Platform bootstrap: Seed migration connector profiles so the Migration Cloud has
starter profiles (CSV/XLSX, student/finance/attendance/grades, generic SIS).
Idempotent (update_or_create by slug). Run: python manage.py seed_migration_profiles
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.automation.models import MigrationProfile


# Official starter migration profiles (audit pack: CSV, XLSX, student/finance/attendance/grades, generic SIS)
MIGRATION_PROFILES = [
    {
        "slug": "students",
        "name": "Student import",
        "description": "Import students from CSV or XLSX (first_name, last_name, admission_number, classroom, etc.).",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "config": {
            "label": "Students",
            "target_fields": ["first_name", "last_name", "admission_number", "academic_year", "classroom", "specialty", "status"],
            "required": ["first_name", "last_name"],
        },
        "sort_order": 10,
    },
    {
        "slug": "grades",
        "name": "Grades import",
        "description": "Import grades from CSV or XLSX (student_code, subject_assignment_id, term_id, scores).",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "config": {
            "label": "Grades",
            "target_fields": [
                "student_code", "subject_assignment_id", "term_id", "teacher_username",
                "seq1", "seq2", "exam", "mock", "practical", "test1", "test2", "remarks",
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
        },
        "sort_order": 20,
    },
    {
        "slug": "finance_import",
        "name": "Finance import",
        "description": "Import fee structures, payments, or chart of accounts from CSV/XLSX.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.FINANCE,
        "config": {"label": "Finance", "target_fields": [], "required": []},
        "sort_order": 30,
    },
    {
        "slug": "attendance_import",
        "name": "Attendance import",
        "description": "Import attendance records from CSV or XLSX.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.ATTENDANCE,
        "config": {"label": "Attendance", "target_fields": [], "required": []},
        "sort_order": 40,
    },
    {
        "slug": "generic_sis",
        "name": "Generic SIS profile",
        "description": "Generic SIS connector for mapping external student information system data.",
        "format": MigrationProfile.Format.GENERIC_SIS,
        "domain": MigrationProfile.Domain.GENERIC_SIS,
        "config": {"label": "Generic SIS", "target_fields": [], "required": []},
        "sort_order": 50,
    },
]


class Command(BaseCommand):
    help = (
        "Seed migration connector profiles so Migration Cloud has starter profiles. "
        "Idempotent (update_or_create by slug)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")

        created = 0
        for row in MIGRATION_PROFILES:
            slug = row["slug"]
            if dry_run:
                if not MigrationProfile.objects.filter(slug=slug).exists():
                    self.stdout.write(f"Would create migration profile: {row['name']} ({slug})")
                    created += 1
                continue
            _, was_created = MigrationProfile.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": row["name"],
                    "description": row.get("description", ""),
                    "format": row.get("format", MigrationProfile.Format.CSV),
                    "domain": row.get("domain", MigrationProfile.Domain.STUDENTS),
                    "config": row.get("config", {}),
                    "is_active": True,
                    "sort_order": row.get("sort_order", 0),
                },
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Migration profiles: {len(MIGRATION_PROFILES)} ensured ({created} created)."
            )
        )
