"""Find and unstick stalled/dead school-provisioning jobs.

Operator tool + prod-safe manual trigger for the provisioning watchdog. Lists every
provisioning WorkflowRun whose heartbeat is dead (process died mid-migrate) or whose
status is failed/stuck, plus any tenant left half-provisioned, and re-drives each one
through the canonical single-flighted resume.

    python manage.py unstick_provisions              # report + unstick
    python manage.py unstick_provisions --dry-run    # report only, change nothing
    python manage.py unstick_provisions --limit 200

Safe to run repeatedly: every resume is single-flighted per school, so a live/healthy
provision is never disturbed and duplicate runs collapse to one.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

PROVISION_WORKFLOW_KEY = "tenant_school_provision"


class Command(BaseCommand):
    help = "Find stalled/dead provisioning jobs and re-drive them via the watchdog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; do not resume.")
        parser.add_argument("--limit", type=int, default=100, help="Max jobs to inspect/resume.")

    def handle(self, *args, **opts):
        from apps.platform_runtime.models import WorkflowRun
        from apps.schools import provision_watchdog as pw
        from apps.schools.models import School

        dry = bool(opts["dry_run"])
        limit = int(opts["limit"])
        stale_s = pw.provision_resume_stale_seconds()
        cutoff = timezone.now() - timedelta(seconds=stale_s)

        # Heartbeat-dead RUNNING runs + failed/stuck runs = candidates to unstick.
        # tenant-isolation-allow: operator-unstick-command-cross-tenant-stuck-provisions
        dead_running = list(
            WorkflowRun.objects.filter(
                workflow_key=PROVISION_WORKFLOW_KEY,
                status="running",
                last_heartbeat_at__lt=cutoff,
            ).order_by("last_heartbeat_at")[:limit]
        )
        # tenant-isolation-allow: operator-unstick-command-cross-tenant-failed-stuck
        failed_stuck = list(
            WorkflowRun.objects.filter(
                workflow_key=PROVISION_WORKFLOW_KEY,
                status__in=("failed", "stuck"),
            ).order_by("-started_at")[:limit]
        )

        self.stdout.write(self.style.HTTP_INFO(
            f"Stale threshold: {stale_s}s. "
            f"Found {len(dead_running)} heartbeat-dead running + {len(failed_stuck)} failed/stuck "
            f"provisioning runs."
        ))
        for run in dead_running:
            age = self._age(run)
            self.stdout.write(
                f"  DEAD  school={run.school_id} step={run.current_step_name} "
                f"heartbeat_age={age}s run={run.pk}"
            )
        for run in failed_stuck:
            self.stdout.write(
                f"  {run.status.upper():6} school={run.school_id} step={run.current_step_name} run={run.pk}"
            )

        # Deduplicate by school and resume.
        school_ids: list[str] = []
        for run in [*dead_running, *failed_stuck]:
            sid = str(run.school_id or "")
            if sid and sid not in school_ids:
                school_ids.append(sid)

        if dry:
            self.stdout.write(self.style.WARNING(
                f"--dry-run: would resume {len(school_ids)} school(s). No changes made."
            ))
            return

        resumed, skipped = 0, 0
        for sid in school_ids[:limit]:
            school = School.objects.filter(pk=sid).first()
            if school is None:
                continue
            result = pw.resume_provision_if_stuck(school, reason="operator-unstick")
            action = result.get("action")
            if action == "resumed":
                resumed += 1
                self.stdout.write(self.style.SUCCESS(f"  resumed school={sid} (attempt {result.get('attempt')})"))
            else:
                skipped += 1
                self.stdout.write(f"  skipped school={sid} ({action}:{result.get('reason')})")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Resumed {resumed}, skipped {skipped} (live/settled/debounced/capped)."
        ))

    def _age(self, run) -> int:
        last = getattr(run, "last_heartbeat_at", None)
        if last is None:
            return -1
        try:
            return int((timezone.now() - last).total_seconds())
        except (TypeError, ValueError):
            return -1
