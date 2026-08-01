"""Export a tenant's full operational dataset to an encrypted+signed .rmcbundle.

The full-fidelity counterpart to the DR snapshot — carries EVERY tenant table so a
running school can be moved onto an on-prem edge box. See
docs/plans/TIER3_TENANT_PORTABILITY_AND_EDGE_SYNC.md.

    python manage.py export_tenant_bundle --slug gilead-tech --out gilead.rmcbundle
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Export a tenant's full operational dataset to an encrypted .rmcbundle file."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug to export.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument("--out", required=True, help="Destination .rmcbundle path.")

    def handle(self, *args, **options):
        from apps.lifecycle.tenant_portability import export_tenant_bundle
        from apps.schools.models import School

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")

        school = (
            School.objects.filter(slug=slug).first()
            if slug
            else School.objects.filter(pk=school_id).first()
        )
        if school is None:
            raise CommandError(f"School not found ({slug or school_id}).")

        data = export_tenant_bundle(school)
        out = Path(options["out"])
        out.write_bytes(data)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {school.slug} → {out} ({len(data):,} bytes, encrypted + signed)."
            )
        )
