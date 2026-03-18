"""
Phase 10 — 4.1: Create PENDING OrchestrationRun(s) by definition code (cron/Celery trigger).
Example: trigger_orchestration_runs --code fee_follow_up (one run per active school).
"""

from django.core.management.base import BaseCommand

from apps.orchestration.models import ProcessDefinition
from apps.orchestration.runners import start_run
from apps.schools.models import School


class Command(BaseCommand):
    help = "Create PENDING orchestration runs for a definition (e.g. fee_follow_up). Use from cron/Celery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--code",
            type=str,
            required=True,
            help="ProcessDefinition code (e.g. fee_follow_up, admissions).",
        )
        parser.add_argument(
            "--school-id",
            type=str,
            default=None,
            help="Optional: run for this school only (UUID).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Only report what would be created."
        )

    def handle(self, *args, **options):
        code = options["code"]
        school_id = options.get("school_id")
        dry_run = options.get("dry_run", False)
        try:
            ProcessDefinition.objects.get(code=code)
        except ProcessDefinition.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Unknown definition: {code}. Run seed_process_definitions."
                )
            )
            return
        schools = []
        if school_id:
            s = School.objects.filter(id=school_id, is_active=True).first()
            if s:
                schools = [s]
        else:
            schools = list(School.objects.filter(is_active=True)[:50])
        created = 0
        for school in schools:
            if dry_run:
                self.stdout.write(f"Would create run: {code} for school {school.id}")
                created += 1
                continue
            run = start_run(code, school=school, triggered_by=None, input_payload={})
            if run:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Trigger: {created} run(s) for {code}."))
