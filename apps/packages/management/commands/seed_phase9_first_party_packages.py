"""
Phase 9 — seed PackageVersion rows for first-party blueprint/workflow/dashboard/policy/etc. packs.
Idempotent (update_or_create on package_id + version). Run after migrations.

  python manage.py seed_phase9_first_party_packages
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.packages.models import PackageVersion

# Ordered so dependency chains are visible in metadata tooling.
PHASE9_PACKAGES: list[dict[str, object]] = [
    {
        "package_id": "fp-blueprint-core-admissions",
        "version": "1.0.0",
        "dependencies": [],
        "changelog_summary": "Blueprint pack: admissions + inquiry defaults",
        "payload_sections": {"blueprint": {"family": "admissions_core"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-workflow-attendance-nudge",
        "version": "1.0.0",
        "dependencies": ["fp-blueprint-core-admissions"],
        "changelog_summary": "Workflow pack: attendance intervention ladder",
        "payload_sections": {"workflow": {"pack": "attendance_nudge"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-dashboard-role-home-ops",
        "version": "1.0.0",
        "dependencies": ["fp-workflow-attendance-nudge"],
        "changelog_summary": "Dashboard pack: role-home operations tiles",
        "payload_sections": {"dashboard": {"surface": "role_home_ops"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-policy-data-retention-starter",
        "version": "1.0.0",
        "dependencies": [],
        "changelog_summary": "Policy bundle: retention + export posture starter",
        "payload_sections": {"policy": {"bundle": "data_retention_starter"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-report-term-summary-kit",
        "version": "1.0.0",
        "dependencies": ["fp-dashboard-role-home-ops"],
        "changelog_summary": "Report/document pack: term summary templates",
        "payload_sections": {"reports": {"kit": "term_summary"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-theme-portal-contrast-v1",
        "version": "1.0.0",
        "dependencies": [],
        "changelog_summary": "Theme / experience pack: high-contrast portal tokens",
        "payload_sections": {"theme": {"preset": "portal_contrast_v1"}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-migration-csv-profiles-v1",
        "version": "1.0.0",
        "dependencies": ["fp-policy-data-retention-starter"],
        "changelog_summary": "Migration pack: CSV profile hints + validation hooks",
        "payload_sections": {"migration": {"profiles_version": 1}},
        "compatibility": {"min_platform": "2025.03"},
    },
    {
        "package_id": "fp-document-parent-handbook-kit",
        "version": "1.0.0",
        "dependencies": ["fp-theme-portal-contrast-v1"],
        "changelog_summary": "Document pack: parent handbook blocks",
        "payload_sections": {"documents": {"kit": "parent_handbook"}},
        "compatibility": {"min_platform": "2025.03"},
    },
]


class Command(BaseCommand):
    help = "Seed first-party PackageVersion rows (Phase 9 ecosystem packs)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        n = 0
        for row in PHASE9_PACKAGES:
            pid = str(row["package_id"])
            ver = str(row["version"])
            if dry_run:
                self.stdout.write(f"Would upsert {pid}@{ver}")
                n += 1
                continue
            PackageVersion.objects.update_or_create(
                package_id=pid,
                version=ver,
                defaults={
                    "dependencies": list(row.get("dependencies") or []),
                    "compatibility": dict(row.get("compatibility") or {}),
                    "payload_sections": dict(row.get("payload_sections") or {}),
                    "changelog_summary": str(row.get("changelog_summary") or "")[:500],
                },
            )
            n += 1
        self.stdout.write(
            self.style.SUCCESS(f"Phase 9 package versions ensured: {n} row(s).")
        )
