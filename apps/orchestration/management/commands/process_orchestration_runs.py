"""
Phase 10 — 4.1: Process pending orchestration runs (one run per definition type per invocation).
Use from cron or Celery beat to drive fee_follow_up, admissions, etc.
"""
from django.core.management.base import BaseCommand

from apps.orchestration.models import OrchestrationRun
from apps.orchestration.runners import get_runner


class Command(BaseCommand):
    help = "Process one pending OrchestrationRun per definition (Phase 10 — 4.1)."

    def add_arguments(self, parser):
        parser.add_argument("--code", type=str, default=None, help="Process only this definition code.")
        parser.add_argument("--limit", type=int, default=5, help="Max runs to process (default 5).")

    def handle(self, *args, **options):
        qs = OrchestrationRun.objects.filter(
            status__in=(OrchestrationRun.Status.PENDING, OrchestrationRun.Status.RUNNING),
        ).select_related("definition").order_by("created_at")
        if options.get("code"):
            qs = qs.filter(definition__code=options["code"])
        processed = 0
        for run in qs[: options["limit"]]:
            runner = get_runner(run)
            if runner is None:
                continue
            if runner.execute():
                processed += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} run(s)."))
