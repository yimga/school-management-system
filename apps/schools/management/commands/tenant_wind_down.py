"""
Tenant Wind-Down: export tenant data (portability) and optionally deactivate.

Usage:
    manage.py tenant_wind_down --school-id <id> [--export-only] [--no-deactivate]
    manage.py tenant_wind_down --slug <slug> [--export-only]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School
from apps.schools.tenant_offboarding import run_wind_down_deactivate, run_wind_down_export


class Command(BaseCommand):
    help = (
        "Tenant Wind-Down: full portability export and optional deactivate (Part F 17.2)."
    )

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

        result = run_wind_down_export(school, full=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {result.student_export_count} students to {result.export_zip_path}"
            )
        )

        if not export_only:
            outcome = run_wind_down_deactivate(school)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tenant {school.slug} deactivated: {outcome.get('message', 'ok')}"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Export complete (tenant left active)."))
