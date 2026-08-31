"""Work a bundle's held rows outside any request, in bounded sweeps.

``auto_remediate_on_review_open`` refuses above ``REVIEW_OPEN_ROW_BUDGET``
because a page open must not run work sized by the data -- production bundle 83
carries 75,600 held rows, and that pass writes. Refusing was the honest answer,
but on its own it would have left those rows with nowhere to go, which is the
original bug wearing a politer face. This is where they go.

It calls the SAME entry point with ``enforce_row_budget=False`` -- the same five
rules in the same order, not a second engine that can drift. What makes that safe
here and unsafe on a page open is only where it runs: this process has no proxy
to kill it halfway, so it cannot leave some rows closed and the rest held with
nothing said.

``--dry-run`` runs the read-only preview instead and writes nothing.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.auto_remediate import (
    auto_remediate_on_review_open,
    preview_autopilot_decisions,
)
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.quarantine_resolution import (
    format_bundle_choices,
    pending_quarantine_count,
)


class Command(BaseCommand):
    help = (
        "Run zero-touch autopilot over a bundle's held rows outside a request. "
        "For bundles too large to triage on page open."
    )

    def add_arguments(self, parser):
        # Optional on purpose -- see profile_bundle_quarantine.
        parser.add_argument("--bundle-id", type=int, default=None)
        parser.add_argument(
            "--max-sweeps",
            type=int,
            default=5,
            help=(
                "Stop after this many sweeps (default 5). One sweep runs all five "
                "rules across every pending row -- it is not a per-row cap, so a "
                "single sweep of a 75,600-row bundle does all 75,600."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what WOULD happen using the read-only preview. Writes nothing.",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        bundle_id = options["bundle_id"]
        if bundle_id is None:
            self.stdout.write(format_bundle_choices())
            return
        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()
        if bundle is None:
            self.stdout.write(format_bundle_choices())
            raise CommandError(f"Bundle {bundle_id} not found -- see the list above.")

        if options["dry_run"]:
            report = preview_autopilot_decisions(bundle)
            if options["as_json"]:
                self.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str))
                return
            counts = report["counts"]
            self.stdout.write(
                f"Bundle {bundle_id} — {report['pending']} held; would close "
                f"{counts['auto_close']}, attempt {counts['auto_replay']} replay(s), "
                f"leave {counts['needs_person']} for a person. Nothing was changed."
            )
            return

        max_sweeps = max(1, int(options["max_sweeps"] or 1))
        pending_before = pending_quarantine_count(bundle)
        sweeps = 0
        resolved_total = 0
        passes: list[dict] = []

        while sweeps < max_sweeps:
            results = auto_remediate_on_review_open(bundle, enforce_row_budget=False)
            sweeps += 1
            resolved = int(results.get("auto_resolved_total") or 0)
            resolved_total += resolved
            passes.append(results)
            # A sweep that resolved nothing will resolve nothing next time either;
            # the rows that are left need a person. Looping would spin forever.
            if resolved <= 0:
                break

        pending_after = pending_quarantine_count(bundle)
        payload = {
            "bundle_id": bundle_id,
            "sweeps": sweeps,
            "resolved": resolved_total,
            "pending_before": pending_before,
            "pending_after": pending_after,
            "more_remaining": pending_after > 0,
            "hit_sweep_ceiling": sweeps >= max_sweeps and resolved_total > 0,
            "passes": passes,
        }

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return

        self.stdout.write(
            f"Bundle {bundle_id} — resolved {resolved_total} row(s) in {sweeps} sweep(s); "
            f"{pending_before} → {pending_after} still held."
        )
        if pending_after:
            self.stdout.write(
                f"  {pending_after} row(s) remain. "
                f"`preview_quarantine_autopilot --bundle-id {bundle_id}` says why."
            )
        if payload["hit_sweep_ceiling"]:
            # Never a silent cap.
            self.stdout.write(
                f"  Stopped at the {max_sweeps}-sweep ceiling while still making "
                "progress — re-run to continue."
            )
