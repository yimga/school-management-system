"""
Phase 10 — 4.1: Process pending orchestration runs (one run per definition type per invocation).
Use from cron or Celery beat to drive fee_follow_up, admissions, etc.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orchestration import event_log
from apps.orchestration.models import OrchestrationRun, OrchestrationStepEvent
from apps.orchestration.runners import get_runner


def fail_unrunnable_run(run) -> None:
    """Fail a run whose definition has no registered runner.

    ``get_runner`` returns ``None`` for a definition with no runner, so such a run
    can never execute. Leaving it PENDING forever permanently inflates the SLO
    queue-depth metric (the aggregator counts PENDING/RUNNING as queued), which is
    exactly what the seeded-but-runner-less ``migration_run`` definition did. Mark
    it FAILED with a reason and emit a RUN_FAILED event (best-effort).
    """
    code = getattr(run.definition, "code", "") if run.definition_id else ""
    run.status = OrchestrationRun.Status.FAILED
    run.error_message = f"No runner registered for definition '{code}'."
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error_message", "completed_at"])
    try:
        event_log.emit(
            run,
            event_type=OrchestrationStepEvent.EventType.RUN_FAILED,
            payload={"reason": "no_runner", "code": code},
        )
    except Exception:  # noqa: BLE001 — event log must never fail the drain
        pass


class Command(BaseCommand):
    help = "Process one pending OrchestrationRun per definition (Phase 10 — 4.1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--code", type=str, default=None, help="Process only this definition code."
        )
        parser.add_argument(
            "--limit", type=int, default=5, help="Max runs to process (default 5)."
        )

    def handle(self, *args, **options):
        qs = (
            OrchestrationRun.objects.filter(
                status__in=(
                    OrchestrationRun.Status.PENDING,
                    OrchestrationRun.Status.RUNNING,
                ),
            )
            .select_related("definition")
            .order_by("created_at")
        )
        if options.get("code"):
            qs = qs.filter(definition__code=options["code"])
        processed = 0
        failed_unrunnable = 0
        for run in qs[: options["limit"]]:
            runner = get_runner(run)
            if runner is None:
                fail_unrunnable_run(run)
                failed_unrunnable += 1
                continue
            if runner.execute():
                processed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} run(s); failed {failed_unrunnable} unrunnable."
            )
        )
