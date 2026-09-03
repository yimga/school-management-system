"""Run the post-deploy tenant import closure playbook for one school.

Order (each step is idempotent):

1. ``remediate_inverted_academic_catalog`` — CM/TVET subject↔specialty inversion
2. ``remediate_finance_ledger_closure`` — issue imported fees + ledger posts
3. ``remediate_quarantine_batch`` — zero-touch autopilot over held rows

Typical production run after batches 1821–1823 land::

    manage.py remediate_tenant_post_import --school gilead-tech --dry-run
    manage.py remediate_tenant_post_import --school gilead-tech --apply

Preview held-row outcomes first (writes nothing)::

    manage.py preview_quarantine_autopilot --school gilead-tech
"""

from __future__ import annotations

import json

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Catalog repair + finance ledger closure + quarantine autopilot for one tenant."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            required=True,
            help="School slug, subdomain, or pk (e.g. gilead-tech).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned work; quarantine step uses read-only preview only.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Execute all three steps.",
        )
        parser.add_argument(
            "--max-sweeps",
            type=int,
            default=5,
            help="Passed through to remediate_quarantine_batch (default 5).",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["apply"]:
            raise CommandError("Pass --dry-run or --apply.")

        school = str(options["school"]).strip()
        dry_run = bool(options["dry_run"])
        mode_flag = "--dry-run" if dry_run else "--apply"
        report: dict[str, object] = {"school": school, "dry_run": dry_run, "steps": []}

        self.stdout.write(f"=== 1/3 academic catalog ({mode_flag}) ===")
        call_command(
            "remediate_inverted_academic_catalog",
            school=school,
            **({"dry_run": True} if dry_run else {"apply": True}),
            stdout=self.stdout,
        )
        report["steps"].append("catalog")

        self.stdout.write(f"\n=== 2/3 finance ledger ({mode_flag}) ===")
        call_command(
            "remediate_finance_ledger_closure",
            school=school,
            **({"dry_run": True} if dry_run else {"apply": True}),
            stdout=self.stdout,
        )
        report["steps"].append("finance_ledger")

        self.stdout.write(f"\n=== 3/3 quarantine autopilot ===")
        if dry_run:
            call_command(
                "preview_quarantine_autopilot",
                school=school,
                stdout=self.stdout,
            )
            report["steps"].append("quarantine_preview")
        else:
            call_command(
                "remediate_quarantine_batch",
                school=school,
                max_sweeps=int(options["max_sweeps"] or 5),
                stdout=self.stdout,
            )
            report["steps"].append("quarantine_apply")

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
