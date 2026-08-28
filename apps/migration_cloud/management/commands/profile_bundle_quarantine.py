"""Profile held-row distribution: issue_class × artifact × domain."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.quarantine_profile import profile_quarantine_distribution


class Command(BaseCommand):
    help = (
        "Print quarantine distribution for a bundle "
        "(issue_class × domain × artifact). Use to triage PDF noise vs real gaps."
    )

    def add_arguments(self, parser):
        parser.add_argument("--bundle-id", type=int, required=True)
        parser.add_argument(
            "--include-resolved",
            action="store_true",
            help="Include repaired/denied rows, not just pending.",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        bundle_id = options["bundle_id"]
        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()
        if bundle is None:
            raise CommandError(f"Bundle {bundle_id} not found")

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
