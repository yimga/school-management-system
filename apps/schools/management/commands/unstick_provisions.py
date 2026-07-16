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

        # Never-provisioned ACTIVE schools carry no run at all, so the run-driven
        # queries above are structurally blind to them — yet they are the most
        # broken tenants on the platform (live, and 500-ing on every request).
        # School.is_active defaults to True, and schools/0012_seed_default_gilead_school
        # seeds exactly one such row into every deployment.
        husks = self._husk_school_ids(limit)
        for sid in husks:
            if sid not in school_ids:
                school_ids.append(sid)
        if husks:
            self.stdout.write(self.style.HTTP_INFO(
                f"Found {len(husks)} active school(s) with NO tenant workspace "
                f"(never provisioned):"
            ))
            for sid in husks:
                school = School.objects.filter(pk=sid).only("slug", "name").first()
                self.stdout.write(
                    f"  HUSK  school={sid} slug={getattr(school, 'slug', '?')}"
                )

        if dry:
            # Report what would ACTUALLY happen, not how many candidates were
            # found. The two are different, and the gap was misleading: the
            # resume path no-ops on a settled school (a fully-live tenant whose
            # run row was merely left FAILED), so "would resume 3" routinely
            # meant "would resume 0" — telling an operator to expect a repair
            # that was never going to run.
            would, settled = [], []
            for sid in school_ids[:limit]:
                school = School.objects.filter(pk=sid).first()
                if school is None:
                    continue
                if pw._school_is_settled(school):
                    settled.append(sid)
                else:
                    would.append(sid)
            self.stdout.write(self.style.WARNING(
                f"--dry-run: would resume {len(would)} school(s); "
                f"{len(settled)} already fully provisioned (their run row is stale "
                f"-- the tenant is fine). No changes made."
            ))
            for sid in would:
                self.stdout.write(f"  would resume school={sid}")
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

    def _husk_school_ids(self, limit: int) -> list[str]:
        """Active schools whose tenant workspace is PROVABLY absent.

        Bounded Python scan: "no workspace" is not a SQL-expressible property.
        The probe is tri-state and answers None outside schema mode, so this
        finds nothing (correctly) on a non-PostgreSQL / RLS-mode connection
        rather than reporting every school as a husk.
        """
        from apps.schools.models import School
        from apps.schools.tenant_workspace import tenant_workspace_exists

        found: list[str] = []
        # tenant-isolation-allow: operator-unstick-command-cross-tenant-husk-scan
        rows = School.objects.filter(is_active=True).order_by("updated_at")[
            : max(limit * 20, 100)  # magic-number-allow: husk-scan-row-cap
        ]
        for school in rows.iterator():
            if len(found) >= limit:
                break
            prov = (getattr(school, "settings", None) or {}).get("provisioning") or {}
            if prov.get("phase_a_complete"):
                continue
            if tenant_workspace_exists(school) is False:
                found.append(str(school.pk))
        return found

    def _age(self, run) -> int:
        last = getattr(run, "last_heartbeat_at", None)
        if last is None:
            return -1
        try:
            return int((timezone.now() - last).total_seconds())
        except (TypeError, ValueError):
            return -1
