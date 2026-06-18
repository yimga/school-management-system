"""Run the in-process periodic-job registry from the CLI (Option 3).

The entry point for:
  * Render cron (``type: cron`` block in render.yaml — runs in its OWN process,
    so heavier jobs don't share the web dyno's threads), and
  * manual ops (``python manage.py run_periodic_jobs``).

Converges on the SAME registry + per-job locking as the in-process scheduler and
the secured cron endpoint — so running it here can't double-fire a job that the
health-triggered tick is also eligible to run.

  python manage.py run_periodic_jobs                 # run every DUE job
  python manage.py run_periodic_jobs --force         # run every job now
  python manage.py run_periodic_jobs --job <name>    # run one job (if due)
  python manage.py run_periodic_jobs --job <name> --force
  python manage.py run_periodic_jobs --list          # show schedule state, run nothing
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run due in-process periodic jobs (or a named job). See module docstring."

    def add_arguments(self, parser):
        parser.add_argument("--job", type=str, default="", help="Run only this registered job.")
        parser.add_argument("--force", action="store_true", help="Run even if not yet due.")
        parser.add_argument("--list", action="store_true", help="List jobs + schedule state, run nothing.")

    def handle(self, *args, **options):
        from apps.platform_runtime import periodic

        if options.get("list"):
            self.stdout.write(json.dumps(periodic.registry_status(), indent=2, default=str))
            return

        force = bool(options.get("force"))
        job = (options.get("job") or "").strip()

        if job:
            results = [periodic.run_job(job, force=force)]
        else:
            results = periodic.run_due_jobs(force=force)

        ran = [r for r in results if r.get("status") == "ran"]
        errored = [r for r in results if r.get("status") == "error"]
        self.stdout.write(json.dumps(results, indent=2, default=str))
        msg = f"periodic: ran={len(ran)} errored={len(errored)} total={len(results)}"
        if errored:
            self.stderr.write(self.style.WARNING(msg))
        else:
            self.stdout.write(self.style.SUCCESS(msg))
