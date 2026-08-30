"""Profile held-row distribution: issue_class × artifact × domain."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.quarantine_profile import profile_quarantine_distribution
from apps.migration_cloud.quarantine_resolution import format_bundle_choices


class Command(BaseCommand):
    help = (
        "Print quarantine distribution for a bundle "
        "(issue_class × domain × artifact). Use to triage PDF noise vs real gaps."
    )

    def add_arguments(self, parser):
        # Optional on purpose: with no id this LISTS bundles, which is the only
        # way an operator on a Render shell or a box can discover a valid one.
        parser.add_argument("--bundle-id", type=int, default=None)
        parser.add_argument(
            "--include-resolved",
            action="store_true",
            help="Include repaired/denied rows, not just pending.",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        bundle_id = options["bundle_id"]
        if bundle_id is None:
            self.stdout.write(format_bundle_choices())
            return
        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()
        if bundle is None:
            # Print the way forward, then still fail: a guessed id is an error and
            # an `&&` chain must not carry on as though it had profiled anything.
            self.stdout.write(format_bundle_choices())
            raise CommandError(f"Bundle {bundle_id} not found -- see the list above.")

        profile = profile_quarantine_distribution(
            bundle,
            pending_only=not options["include_resolved"],
        )

        if options["as_json"]:
            self.stdout.write(json.dumps(profile, indent=2, sort_keys=True))
            return

        self.stdout.write(f"Bundle {bundle_id} — {profile['total']} held row(s)")
        self.stdout.write(f"PDF noise candidates: {profile['pdf_noise_candidates']}")
        self.stdout.write("\nBy issue class:")
        for key, count in profile["by_issue_class"].items():
            label = profile["issue_class_labels"].get(key, key)
            self.stdout.write(f"  {count:4d}  {key} — {label}")
        self.stdout.write("\nBy domain:")
        for key, count in profile["by_domain"].items():
            self.stdout.write(f"  {count:4d}  {key}")
        self.stdout.write("\nBy artifact:")
        for key, count in profile["by_artifact"].items():
            self.stdout.write(f"  {count:4d}  {key}")
        self.stdout.write("\nMatrix (issue_class → domain|artifact):")
        for ic, cells in profile["matrix_issue_class_domain_artifact"].items():
            self.stdout.write(f"  [{ic}]")
            for cell, count in cells.items():
                self.stdout.write(f"    {count:4d}  {cell}")
