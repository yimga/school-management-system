"""What would zero-touch autopilot do to this bundle? Read-only.

The zero-touch spec's last unchecked rule is "every claim about behaviour is
backed by a state read, not by reading the code and reasoning about it". Running
the real pass to find out is not a state read -- it changes the state, and on a
live tenant it closes rows in order to tell you whether it would close them.

    python manage.py preview_quarantine_autopilot --bundle-id 8
    python manage.py preview_quarantine_autopilot --bundle-id 8 --json
    python manage.py preview_quarantine_autopilot --bundle-id 8 --list-held

Writes nothing. Safe against production.

``profile_bundle_quarantine`` answers a narrower question: it counts PDF-noise
candidates, which is one of the five rules autopilot runs.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.auto_remediate import preview_autopilot_decisions
from apps.migration_cloud.models import MigrationBundle


class Command(BaseCommand):
    help = (
        "Preview zero-touch autopilot on a bundle's held rows without resolving "
        "any of them: what closes, what is replayed (and may fail), what needs a person."
    )

    def add_arguments(self, parser):
        # Optional on purpose -- see profile_bundle_quarantine.
        parser.add_argument("--bundle-id", type=int, default=None)
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--list-held",
            action="store_true",
            help="Print one line per row that needs a person, not just the totals.",
        )

    def handle(self, *args, **options):
        from apps.migration_cloud.quarantine_resolution import format_bundle_choices

        bundle_id = options["bundle_id"]
        if bundle_id is None:
            self.stdout.write(format_bundle_choices())
            return
        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()
        if bundle is None:
            self.stdout.write(format_bundle_choices())
            raise CommandError(f"Bundle {bundle_id} not found -- see the list above.")

        report = preview_autopilot_decisions(bundle)

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str))
            return

        counts = report["counts"]
        self.stdout.write(
            f"Bundle {report['bundle_id']} — {report['pending']} row(s) held right now"
        )
        self.stdout.write("")
        self.stdout.write(f"  closes automatically   {counts['auto_close']:5d}")
        self.stdout.write(
            f"  replay attempted       {counts['auto_replay']:5d}"
            "   (re-landed; a failed land stays held)"
        )
        self.stdout.write(f"  needs a person         {counts['needs_person']:5d}")

        if report["by_rule"]:
            self.stdout.write("\nby rule:")
            for rule, count in report["by_rule"].items():
                self.stdout.write(f"  {count:5d}  {rule}")

        guessed = report["auto_decided_on_guessed_class"]
        if guessed:
            self.stdout.write(
                f"\n{guessed} automated decision(s) rest on an issue_class GUESSED from "
                "the error text (reason_source != declared). Those rules re-read the "
                "source row, so the class is a pre-filter and not the evidence."
            )

        withheld = report["held_because_class_was_guessed"]
        if withheld:
            self.stdout.write(
                f"\n{withheld} row(s) stay held because their no-action class was a "
                "GUESS. A UNIQUE-constraint failure reads as duplicate to the fallback "
                "matcher, and a failed write is not an already-applied row."
            )

        if report["needs_person_breakdown"]:
            self.stdout.write("\nstill needs a person (issue_class|domain|artifact):")
            for cell, count in report["needs_person_breakdown"].items():
                self.stdout.write(f"  {count:5d}  {cell}")

        if options["list_held"]:
            self.stdout.write("\nheld rows:")
            for row in report["rows"]:
                if row["outcome"] != "needs_person":
                    continue
                self.stdout.write(
                    f"  #{row['record_id']}  {row['issue_class']}/{row['domain']}"
                    f"  — {row['detail']}"
                )

        if counts["auto_close"] == 0 and counts["auto_replay"] == 0:
            self.stdout.write(
                "\nAutopilot would change nothing here. Every held row needs judgement."
            )
