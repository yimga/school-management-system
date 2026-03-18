"""
Part F Section 17.2: Tenant Wind-Down flow — export tenant data and deactivate.
Usage:
    manage.py tenant_wind_down --school-id <id> [--export-only] [--no-deactivate]
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db import DatabaseError, IntegrityError, OperationalError

from apps.schools.models import School


class Command(BaseCommand):
    help = "Tenant Wind-Down: export tenant data (portability) and optionally deactivate school (Part F 17.2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id", type=int, help="School (tenant) ID to wind down"
        )
        parser.add_argument("--slug", type=str, help="School slug to wind down")
        parser.add_argument(
            "--export-only",
            action="store_true",
            help="Only export data; do not deactivate",
        )
        parser.add_argument(
            "--no-deactivate", action="store_true", help="Same as --export-only"
        )

    def handle(self, *args, **options):
        school_id = options.get("school_id")
        slug = options.get("slug")
        export_only = options.get("export_only") or options.get("no_deactivate")

        if not school_id and not slug:
            raise CommandError("Provide --school-id or --slug")

        try:
            if school_id:
                school = School.objects.get(pk=school_id)
            else:
                school = School.objects.get(slug=slug)
        except School.DoesNotExist as e:
            raise CommandError(f"School not found: {e}")

        with transaction.atomic():
            # Export: trigger data portability (one-click export). Use compliance export per student or bulk.
            try:
                from apps.compliance.gdpr_services import (
                    export_student_data_portability,
                )
                from apps.people.models import StudentProfile
            except ImportError:
                self.stdout.write(
                    self.style.WARNING(
                        "Compliance/people not available; skipping per-student export."
                    )
                )
            else:
                students = StudentProfile.objects.filter(school=school).values_list(
                    "id", flat=True
                )[:1000]
                count = 0
                for sid in students:
                    try:
                        export_student_data_portability(school.id, sid, format="json")
                        count += 1
                    except (
                        OSError,
                        ValueError,
                        TypeError,
                        KeyError,
                        AttributeError,
                        DatabaseError,
                        IntegrityError,
                        OperationalError,
                    ) as e:
                        self.stdout.write(
                            self.style.WARNING(f"Export student {sid} failed: {e}")
                        )
                self.stdout.write(
                    self.style.SUCCESS(f"Exported data for {count} students.")
                )

            if not export_only:
                school.is_active = False
                school.frozen_reason = "Tenant wind-down (Part F 17.2)"
                school.save(update_fields=["is_active", "frozen_reason", "updated_at"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Tenant {school.slug} deactivated (wind-down complete)."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("Export complete (tenant left active).")
                )
