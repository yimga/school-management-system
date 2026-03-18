"""
Seed core entity and field catalog entries (Workstream I — Metadata Catalog).

Run: python manage.py seed_entity_catalog [--dry-run]
Creates EntityCatalogEntry and FieldCatalogEntry for core platform entities so lineage
and dependency tracking can be used (lineage-first rule).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.metadata.models import EntityCatalogEntry, FieldCatalogEntry

# Core entities and their key fields (entity_code -> list of (field_name, label, data_type, is_required))
CATALOG_ENTITIES = [
    (
        "person",
        "Person",
        "Canonical person record (user, guardian, staff).",
        "people",
        "people.User",
        True,
    ),
    (
        "student",
        "Student",
        "Student profile and enrollment.",
        "people",
        "people.StudentProfile",
        True,
    ),
    (
        "parent_guardian",
        "Parent / Guardian",
        "Parent or guardian profile.",
        "people",
        "people.StudentGuardian",
        True,
    ),
    (
        "staff",
        "Staff",
        "Staff/teacher profile.",
        "people",
        "people.TeacherProfile",
        True,
    ),
    (
        "classroom",
        "Classroom",
        "Class or homeroom.",
        "academics",
        "academics.Classroom",
        True,
    ),
    ("section", "Section", "Course section.", "academics", "academics.Section", True),
    (
        "attendance",
        "Attendance",
        "Attendance record.",
        "academics",
        "academics.Attendance",
        True,
    ),
    ("grade", "Grade", "Grade/assessment result.", "evals", "evals.Grade", True),
    ("invoice", "Invoice", "Finance invoice.", "finance", "finance.Invoice", True),
    ("payment", "Payment", "Payment record.", "finance", "finance.Payment", True),
    (
        "application",
        "Application",
        "Admission/application record.",
        "people",
        "people.Applicant",
        True,
    ),
    (
        "communication",
        "Communication",
        "Announcement or message.",
        "communication",
        "communication.Announcement",
        True,
    ),
]

FIELDS_BY_ENTITY = {
    "person": [
        ("first_name", "First name", "string", True),
        ("last_name", "Last name", "string", True),
        ("email", "Email", "string", False),
        ("phone", "Phone", "string", False),
    ],
    "student": [
        ("admission_number", "Admission number", "string", False),
        ("date_of_birth", "Date of birth", "date", False),
        ("gender", "Gender", "string", False),
        ("joined_term", "Joined term", "string", False),
    ],
    "invoice": [
        ("amount", "Amount", "number", True),
        ("due_date", "Due date", "date", False),
        ("status", "Status", "string", False),
    ],
    "payment": [
        ("amount", "Amount", "number", True),
        ("paid_at", "Paid at", "date", False),
        ("method", "Method", "string", False),
    ],
    "attendance": [
        ("date", "Date", "date", True),
        ("status", "Status", "string", True),
    ],
    "grade": [
        ("score", "Score", "number", False),
        ("grade_value", "Grade value", "string", False),
    ],
}


class Command(BaseCommand):
    help = "Seed Metadata Catalog with core entity and field entries (Workstream I)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no changes written."))

        created_entities = 0
        created_fields = 0

        for (
            code,
            name,
            description,
            owning_app,
            model_label,
            is_core,
        ) in CATALOG_ENTITIES:
            ent, created = EntityCatalogEntry.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "owning_app": owning_app,
                    "model_label": model_label,
                    "is_core": is_core,
                },
            )
            if created and not dry_run:
                created_entities += 1
            elif created:
                created_entities += 1

            for field_name, label, data_type, is_required in FIELDS_BY_ENTITY.get(
                code, []
            ):
                _, f_created = FieldCatalogEntry.objects.get_or_create(
                    entity=ent,
                    field_name=field_name,
                    defaults={
                        "label": label,
                        "data_type": data_type,
                        "is_required": is_required,
                        "is_custom": False,
                        "defined_in_app": owning_app,
                        "source": "seed_entity_catalog",
                    },
                )
                if f_created and not dry_run:
                    created_fields += 1
                elif f_created:
                    created_fields += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Would ensure {len(CATALOG_ENTITIES)} entities and their fields."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Entity catalog: {created_entities} new entities, {created_fields} new fields (total entities: {len(CATALOG_ENTITIES)})."
                )
            )
