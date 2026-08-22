"""Reconcile blueprint/pack/marketplace installation layers for one or all schools."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.installation_reconciliation import (
    audit_installation_layers,
    reconcile_school_installations,
)
from apps.schools.models import School


class Command(BaseCommand):
    help = (
        "Audit (and optionally repair) cross-layer installation drift "
        "for blueprint, pack, package, and marketplace markers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school_slug",
            default="",
            help="Limit to one school slug; omit to scan every active school.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Repair drift (default is audit-only).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max schools to process (0 = no limit).",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "").strip()
        repair = bool(options.get("apply"))
        limit = int(options.get("limit") or 0)

        qs = School.objects.filter(is_active=True).order_by("name")
        if slug:
            qs = qs.filter(slug=slug)
        if limit > 0:
            qs = qs[:limit]

        schools = list(qs)
        if not schools:
            self.stderr.write(self.style.ERROR("No matching schools."))
            return

        total_findings = 0
        repaired_schools = 0
        for school in schools:
            if repair:
                report = reconcile_school_installations(
                    school,
                    repair=True,
                    context="management_command",
                )
            else:
                report = audit_installation_layers(school)
            count = int(report.get("finding_count") or 0)
            total_findings += count
            if repair and report.get("repaired"):
                repaired_schools += 1
            status = "OK" if report.get("ok") else f"{count} finding(s)"
            self.stdout.write(f"{school.slug}: {status}")
            for finding in report.get("findings") or []:
                self.stdout.write(f"  - [{finding.get('layer')}] {finding.get('message')}")
            for item in report.get("repaired") or []:
                self.stdout.write(self.style.SUCCESS(f"  repaired: {item}"))

        mode = "reconcile" if repair else "audit"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} complete — schools={len(schools)} findings={total_findings} "
                f"repaired_schools={repaired_schools}"
            )
        )
