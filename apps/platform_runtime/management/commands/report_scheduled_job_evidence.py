"""``report_scheduled_job_evidence`` -- prove which periodic jobs actually RAN.

THE PROBLEM THIS SOLVES. After triggering ``/api/internal/cron/run/`` an operator
has, until now, only green-on-failure signals:

  * the HTTP 200 proves a request was served, not that a job ran; with
    ``{"background": true}`` the 202 is returned BEFORE any job starts;
  * ``run_periodic_jobs`` prints its own results, but only for that one process
    and only while you are watching it;
  * the GET status surface reads the CACHE ``last_run``, which
    ``periodic._claim`` writes BEFORE calling the job -- so a job that raised on
    its first statement still reports a fresh ``last_run`` and ``due_now: false``;
  * the Django admin lists ``ScheduledJobHeartbeat`` ROWS, so a job that has never
    run has no row and is simply absent from the page. That is how 26 registered
    cron-only jobs stayed invisible on the screen built to show job health.

This command joins the REGISTRY against the durable heartbeats and prints one line
per registered job, so a job with no heartbeat is reported LOUDLY as
``never_invoked`` instead of being omitted. It is strictly read-only: unlike
``monitor_scheduled_job_health`` it never spawns recovery threads, so it can be
polled without changing what it measures.

  python manage.py report_scheduled_job_evidence
  python manage.py report_scheduled_job_evidence --cron-only
  python manage.py report_scheduled_job_evidence --json
  python manage.py report_scheduled_job_evidence --fail-on-never-invoked
  python manage.py report_scheduled_job_evidence --fail-unless-succeeded-within 900

``--fail-unless-succeeded-within <seconds>`` is the post-trigger assertion: run the
trigger, then run this, and a zero exit status means every job in scope genuinely
succeeded inside that window. That is the check an external scheduler should run
after its POST, and the one a human should run after a manual one-shot.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

#: Printed when a job has never recorded a successful run.
_NEVER = "never"


class Command(BaseCommand):
    help = "Report durable per-job execution evidence (which periodic jobs actually ran)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit machine-readable JSON (evidence rows + summary).",
        )
        parser.add_argument(
            "--cron-only",
            action="store_true",
            help="Restrict to auto_eligible=False jobs (the ones only an external trigger runs).",
        )
        parser.add_argument(
            "--fail-on-never-invoked",
            action="store_true",
            help="Exit non-zero if any job in scope has never been invoked at all.",
        )
        parser.add_argument(
            "--fail-unless-succeeded-within",
            type=int,
            default=0,
            metavar="SECONDS",
            help=(
                "Exit non-zero unless EVERY job in scope succeeded within this many "
                "seconds. The post-trigger assertion; 0 (default) disables it."
            ),
        )

    def handle(self, *args, **options):
        from apps.platform_runtime.scheduled_job_health import (
            VERDICT_NEVER_INVOKED,
            job_execution_evidence,
            summarize_execution_evidence,
        )

        evidence, _summary = job_execution_evidence()
        if options.get("cron_only"):
            evidence = [r for r in evidence if not r["auto_eligible"]]
        # Recompute so the summary always describes the rows actually shown.
        summary = summarize_execution_evidence(evidence)

        if options.get("as_json"):
            self.stdout.write(
                json.dumps({"evidence": evidence, "summary": summary}, indent=2, default=str)
            )
        else:
            for row in sorted(evidence, key=lambda r: (r["verdict"] != VERDICT_NEVER_INVOKED, r["job"])):
                since = row["seconds_since_success"]
                age = _NEVER if since is None else f"{int(since)}s ago"
                self.stdout.write(
                    f"{row['verdict']:<14} {row['trigger']:<12} {row['job']} "
                    f"(interval={row['interval_seconds']}s, last_success={age}, "
                    f"fails={row['consecutive_failures']})"
                )
                if row["last_error"]:
                    self.stdout.write(f"                             last_error: {row['last_error']}")
            self.stdout.write(
                f"{summary['healthy']} ok / {summary['total']} registered "
                f"({summary['never_invoked']} never invoked, {summary['failing']} failing, "
                f"{summary['stale']} stale; cron-only never invoked: "
                f"{summary['cron_only_never_invoked']}/{summary['cron_only_total']})"
            )

        # --- assertions ------------------------------------------------------
        if options.get("fail_on_never_invoked") and summary["never_invoked"]:
            names = [r["job"] for r in evidence if r["verdict"] == VERDICT_NEVER_INVOKED]
            raise CommandError(
                f"{len(names)} job(s) have never been invoked: {', '.join(sorted(names))}"
            )

        window = int(options.get("fail_unless_succeeded_within") or 0)
        if window > 0:
            missed = [
                r["job"]
                for r in evidence
                if r["seconds_since_success"] is None or r["seconds_since_success"] > window
            ]
            if missed:
                raise CommandError(
                    f"{len(missed)} job(s) did not succeed within {window}s: "
                    f"{', '.join(sorted(missed))}"
                )
