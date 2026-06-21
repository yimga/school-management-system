"""``monitor_scheduled_job_health`` — report / alert on overdue periodic jobs.

Reads the durable ``ScheduledJobHeartbeat`` rows via the dead-man's-switch
monitor and prints a per-job health line. With ``--fail-on-stale`` it exits
non-zero when any registered job is overdue, so an external cron / CI probe can
surface the alarm even when nobody is watching the logs.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Report on periodic-job heartbeats and flag stale (overdue) jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-stale",
            action="store_true",
            help="Exit non-zero if any registered job is overdue.",
        )

    def handle(self, *args, **options):
        from apps.platform_runtime.scheduled_job_health import run_health_monitor

        findings = run_health_monitor()
        for f in sorted(findings, key=lambda x: x.job_name):
            age = int(f.age_seconds) if f.age_seconds is not None else "n/a"
            state = "STALE" if f.is_stale else "ok"
            self.stdout.write(
                f"{f.job_name}: {state} "
                f"(interval={f.interval_seconds}s, age={age}s, "
                f"threshold={int(f.threshold_seconds)}s, reason={f.reason})"
            )
        stale = [f for f in findings if f.is_stale]
        self.stdout.write(f"{len(stale)} stale / {len(findings)} total")
        if stale and options["fail_on_stale"]:
            raise CommandError(f"{len(stale)} scheduled job(s) are stale")
