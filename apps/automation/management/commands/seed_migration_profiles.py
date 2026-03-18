"""
Platform bootstrap: Seed migration connector profiles so the Migration Cloud has
starter profiles (CSV/XLSX, student/finance/attendance/grades, generic SIS).
Idempotent (update_or_create by slug). Run: python manage.py seed_migration_profiles
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.automation.models import MigrationProfile


# Schema hints: source column names → canonical field (for auto-mapping).
# Keys are lowercase/alternate names often seen in exports.
POWERSCHOOL_STUDENT_HINTS = {
    "student_number": "admission_number",
    "student_id": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "firstname": "first_name",
    "lastname": "last_name",
    "grade_level": "academic_year",
    "grade": "academic_year",
    "homeroom": "classroom",
    "class": "classroom",
    "status": "status",
}
BLACKBAUD_STUDENT_HINTS = {
    "student_id": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "grade_level": "academic_year",
    "grade": "academic_year",
    "form": "academic_year",
    "year_group": "academic_year",
    "homeroom": "classroom",
    "advisor": "classroom",
    "status": "status",
}
VERACROSS_STUDENT_HINTS = {
    "person_id": "admission_number",
    "student_id": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "grade": "academic_year",
    "form": "academic_year",
    "section": "classroom",
    "advisor": "classroom",
    "status": "status",
}
INFINITE_CAMPUS_STUDENT_HINTS = {
    "student_id": "admission_number",
    "student_number": "admission_number",
    "firstName": "first_name",
    "lastName": "last_name",
    "grade": "academic_year",
    "schoolYear": "academic_year",
    "homeroom": "classroom",
    "status": "status",
}
FACTS_STUDENT_HINTS = {
    "student_id": "admission_number",
    "student_number": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "grade_level": "academic_year",
    "grade": "academic_year",
    "homeroom": "classroom",
    "status": "status",
}
SKYWARD_STUDENT_HINTS = {
    "student_number": "admission_number",
    "student_id": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "grade_level": "academic_year",
    "grade": "academic_year",
    "homeroom": "classroom",
    "status": "status",
}
ALMA_STUDENT_HINTS = {
    "student_id": "admission_number",
    "first_name": "first_name",
    "last_name": "last_name",
    "grade_level": "academic_year",
    "grade": "academic_year",
    "homeroom": "classroom",
    "status": "status",
}

# Official starter migration profiles (audit pack + Phase A competitor adapters)
MIGRATION_PROFILES = [
    # Generic / Other (no source_system)
    {
        "slug": "students",
        "name": "Student import",
        "description": "Import students from CSV or XLSX (first_name, last_name, admission_number, classroom, etc.).",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": None,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
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
        "source_system": None,
        "config": {
            "label": "Grades",
            "target_fields": [
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
        "source_system": None,
        "config": {"label": "Finance", "target_fields": [], "required": []},
        "sort_order": 30,
    },
    {
        "slug": "attendance_import",
        "name": "Attendance import",
        "description": "Import attendance records from CSV or XLSX.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.ATTENDANCE,
        "source_system": None,
        "config": {"label": "Attendance", "target_fields": [], "required": []},
        "sort_order": 40,
    },
    {
        "slug": "generic_sis",
        "name": "Generic SIS profile",
        "description": "Generic SIS connector for mapping external student information system data.",
        "format": MigrationProfile.Format.GENERIC_SIS,
        "domain": MigrationProfile.Domain.GENERIC_SIS,
        "source_system": None,
        "config": {"label": "Generic SIS", "target_fields": [], "required": []},
        "sort_order": 50,
    },
    # Phase A: PowerSchool adapters
    {
        "slug": "students_from_powerschool",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Student import (from PowerSchool)",
        "description": "Import students from PowerSchool CSV export. Column names are auto-mapped.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.POWERSCHOOL,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": POWERSCHOOL_STUDENT_HINTS,
        },
        "sort_order": 61,
    },
    {
        "slug": "grades_from_powerschool",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Grades import (from PowerSchool)",
        "description": "Import grades from PowerSchool export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.POWERSCHOOL,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "student_number": "student_code",
                "course_name": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 62,
    },
    # Blackbaud adapters
    {
        "slug": "students_from_blackbaud",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Student import (from Blackbaud)",
        "description": "Import students from Blackbaud CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.BLACKBAUD,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": BLACKBAUD_STUDENT_HINTS,
        },
        "sort_order": 71,
    },
    {
        "slug": "grades_from_blackbaud",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Grades import (from Blackbaud)",
        "description": "Import grades from Blackbaud export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.BLACKBAUD,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "course": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 72,
    },
    # Veracross adapters
    {
        "slug": "students_from_veracross",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Student import (from Veracross)",
        "description": "Import students from Veracross CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.VERACROSS,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": VERACROSS_STUDENT_HINTS,
        },
        "sort_order": 81,
    },
    {
        "slug": "grades_from_veracross",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Grades import (from Veracross)",
        "description": "Import grades from Veracross export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.VERACROSS,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "person_id": "student_code",
                "student_id": "student_code",
                "course_id": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 82,
    },
    # Infinite Campus adapters
    {
        "slug": "students_from_infinite_campus",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Student import (from Infinite Campus)",
        "description": "Import students from Infinite Campus CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.INFINITE_CAMPUS,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": INFINITE_CAMPUS_STUDENT_HINTS,
        },
        "sort_order": 91,
    },
    {
        "slug": "grades_from_infinite_campus",
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "name": "Grades import (from Infinite Campus)",
        "description": "Import grades from Infinite Campus export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.INFINITE_CAMPUS,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "section_id": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 92,
    },
    # FACTS adapters
    {
        "slug": "students_from_facts",
        "name": "Student import (from FACTS)",
        "description": "Import students from FACTS CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.FACTS,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": FACTS_STUDENT_HINTS,
        },
        "sort_order": 101,
    },
    {
        "slug": "grades_from_facts",
        "name": "Grades import (from FACTS)",
        "description": "Import grades from FACTS export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.FACTS,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "student_number": "student_code",
                "course": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 102,
    },
    # Skyward adapters
    {
        "slug": "students_from_skyward",
        "name": "Student import (from Skyward)",
        "description": "Import students from Skyward CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.SKYWARD,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": SKYWARD_STUDENT_HINTS,
        },
        "sort_order": 111,
    },
    {
        "slug": "grades_from_skyward",
        "name": "Grades import (from Skyward)",
        "description": "Import grades from Skyward export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.SKYWARD,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "student_number": "student_code",
                "course": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 112,
    },
    # Alma adapters
    {
        "slug": "students_from_alma",
        "name": "Student import (from Alma)",
        "description": "Import students from Alma CSV export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.ALMA,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Students",
            "target_fields": [
                "first_name",
                "last_name",
                "admission_number",
                "academic_year",
                "classroom",
                "specialty",
                "status",
            ],
            "required": ["first_name", "last_name"],
            "schema_hints": ALMA_STUDENT_HINTS,
        },
        "sort_order": 121,
    },
    {
        "slug": "grades_from_alma",
        "name": "Grades import (from Alma)",
        "description": "Import grades from Alma export.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.GRADES,
        "source_system": MigrationProfile.SourceSystem.ALMA,
        "profile_category": MigrationProfile.ProfileCategory.VENDOR,
        "config": {
            "label": "Grades",
            "target_fields": [
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
            ],
            "required": ["student_code", "subject_assignment_id", "term_id"],
            "schema_hints": {
                "student_id": "student_code",
                "course_id": "subject_assignment_id",
                "term": "term_id",
            },
        },
        "sort_order": 122,
    },
    # Generic strategy profile (non-competitor)
    {
        "slug": "phased_migration",
        "name": "Phased migration strategy",
        "description": "Run migrations in phases (e.g. students first, then grades, then finance) with validation between steps.",
        "format": MigrationProfile.Format.CSV,
        "domain": MigrationProfile.Domain.STUDENTS,
        "source_system": MigrationProfile.SourceSystem.OTHER,
        "profile_category": MigrationProfile.ProfileCategory.STRATEGY,
        "config": {
            "label": "Phased",
            "strategy": "phased",
            "target_fields": [],
            "required": [],
        },
        "sort_order": 200,
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
                    self.stdout.write(
                        f"Would create migration profile: {row['name']} ({slug})"
                    )
                    created += 1
                continue
            _, was_created = MigrationProfile.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": row["name"],
                    "description": row.get("description", ""),
                    "format": row.get("format", MigrationProfile.Format.CSV),
                    "domain": row.get("domain", MigrationProfile.Domain.STUDENTS),
                    "source_system": row.get("source_system"),
                    "profile_category": row.get("profile_category"),
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
