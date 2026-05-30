"""Backfill Organization rows from mat_groups JSON and parent_school trees."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.governance.backfill_organizations import backfill_organizations_from_hierarchy


class Command(BaseCommand):
    help = (
        "Create Organization rows and link existing hierarchy schools "
        "(legacy mat_groups JSON + parent_school trees). Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist Organization rows and School.organization links.",
        )
        parser.add_argument(
            "--promote-group-mode",
            action="store_true",
            help="Set governance_operating_mode=group_member on linked standalone schools.",
        )
        parser.add_argument(
            "--mat-groups-only",
            action="store_true",
            help="Only process legacy cockpit_payload mat_groups JSON.",
        )
        parser.add_argument(
            "--parent-school-only",
            action="store_true",
            help="Only process parent_school hierarchies.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        promote = bool(options["promote_group_mode"])
        mat_only = bool(options["mat_groups_only"])
        parent_only = bool(options["parent_school_only"])
        include_mat = not parent_only
        include_parent = not mat_only

        if not apply:
            self.stdout.write("Dry run (pass --apply to write).")

        result = backfill_organizations_from_hierarchy(
            apply=apply,
            promote_group_mode=promote,
            include_mat_groups=include_mat,
            include_parent_school=include_parent,
        )
        self.stdout.write(json.dumps(result.as_dict(), indent=2))
