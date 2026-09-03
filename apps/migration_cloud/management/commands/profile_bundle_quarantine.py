"""Profile held-row distribution: issue_class × artifact × domain."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.quarantine_profile import (
    artifact_yield_overview,
    profile_quarantine_distribution,
)
from apps.migration_cloud.quarantine_resolution import (
    format_bundle_choices,
    resolve_school_and_bundle,
)


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
            "--school",
            type=str,
            default=None,
            help=(
                "Tenant slug or subdomain — resolves the newest bundle when "
                "--bundle-id is omitted (e.g. gilead-tech)."
            ),
        )
        parser.add_argument(
            "--include-resolved",
            action="store_true",
            help="Include repaired/denied rows, not just pending.",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        bundle_id = options["bundle_id"]
        school_slug = options.get("school")
        if bundle_id is None and school_slug:
            school, bundle = resolve_school_and_bundle(school_slug)
            if school is None:
                self.stdout.write(format_bundle_choices())
                raise CommandError(
                    f"Unknown school {school_slug!r} — see the bundle list above."
                )
            if bundle is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"School {school.slug!r} has no migration bundles — "
                        "nothing to profile."
                    )
                )
                return
            bundle_id = bundle.pk
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

        yields = artifact_yield_overview(bundle)

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {**profile, "artifact_yield": yields}, indent=2, sort_keys=True
                )
            )
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
        reports = [
            row
            for row in yields
            if row["skipped_as_report"] and not row["produced_nothing"]
        ]
        if reports:
            # Zero records BY DESIGN. Named so a reader of the section below does
            # not have to wonder whether these were missed too.
            self.stdout.write("\nSkipped as derived reports (zero records is correct):")
            for row in reports:
                self.stdout.write(
                    f"  {row['artifact']}  — {row['rows_discovered']} row(s) read, "
                    "landed by design as a report"
                )

        unreadable = [row for row in yields if row["unreadable"]]
        if unreadable:
            self.stdout.write("\nCould not be read at all:")
            for row in unreadable:
                self.stdout.write(f"  {row['artifact']}  — {row['unreadable_reason']}")

        barren = [row for row in yields if row["produced_nothing"]]
        if barren:
            # Every discovered row of these files was quarantined, so they created
            # nothing. Once autopilot dismisses those rows the bundle reads APPLIED
            # with an empty queue, and this is the only place that still says so.
            self.stdout.write(
                "\nProduced NO records (every discovered row was quarantined):"
            )
            for row in barren:
                self.stdout.write(
                    f"  {row['artifact']}  — {row['rows_discovered']} row(s) read, "
                    f"{row['held_total']} held ({row['held_resolved']} already resolved)"
                )
            self.stdout.write(
                "  If one of these was meant to carry data, its mapping failed — a "
                "clean queue is not the same as an import."
            )

        self.stdout.write("\nMatrix (issue_class → domain|artifact):")
        for ic, cells in profile["matrix_issue_class_domain_artifact"].items():
            self.stdout.write(f"  [{ic}]")
            for cell, count in cells.items():
                self.stdout.write(f"    {count:4d}  {cell}")
