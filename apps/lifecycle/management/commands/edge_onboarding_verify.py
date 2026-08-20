"""Verify edge-onboarding steps for one school — the real replacement for ``shell -c``.

Cloud/operator default: no network, no ``EdgeSyncRun`` write (``include_gate`` off).
On the box, pass ``--include-gate`` to run the dry sync probe and go-dark checks.

    python manage.py edge_onboarding_verify --slug gilead-tech
    python manage.py edge_onboarding_verify --slug gilead-tech --include-gate
"""
from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify edge onboarding steps for a school (no network unless --include-gate)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="School slug.")
        parser.add_argument(
            "--include-gate",
            action="store_true",
            help="Run box-side network steps (dry gate, live proof, go-dark). Never use on a cloud GET.",
        )
        parser.add_argument(
            "--host-kind",
            dest="host_kind",
            default="",
            help="Optional: 'manager' skips box-settings evidence (SECRET_KEY theater).",
        )
        parser.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    def handle(self, *args, **options):
        from apps.lifecycle.edge_onboarding import run_verification_suite
        from apps.schools.models import School

        slug = (options.get("slug") or "").strip()
        school = School.objects.filter(slug=slug).first()
        if school is None:
            raise CommandError(f"School not found: {slug}")

        result = run_verification_suite(
            school,
            include_gate=bool(options.get("include_gate")),
            host_kind=(options.get("host_kind") or "").strip() or None,
        )
        if options.get("json"):
            self.stdout.write(json.dumps(result, default=str))
        else:
            self.stdout.write(
                f"edge_onboarding_verify {slug}: "
                f"{result.get('passed', 0)}/{result.get('evaluated', result.get('total', 0))} "
                f"evaluated passing (total rows={result.get('total', 0)}, "
                f"skipped={result.get('skipped', 0)})"
            )
            for row in result.get("steps") or []:
                if row.get("skipped"):
                    flag = "SKIP"
                else:
                    flag = "PASS" if row.get("ok") else "FAIL"
                self.stdout.write(f"  [{flag}] {row.get('key')}: {row.get('detail')}")

        if not result.get("ok"):
            sys.exit(1)
