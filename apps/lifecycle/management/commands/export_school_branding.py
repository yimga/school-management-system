"""Export a school's branding (logo + colours + brand profile) to a .rmcbrand file.

The third portability artifact alongside the tenant DATA bundle (.rmcbundle) and the
identity bundle — neither of those carries branding/media, so a self-hosted / offline
box would otherwise lose the school's logo and colours. The logo is packaged so it
renders on the box with NO internet (DB-resident data URI) plus the raw bytes.

    python manage.py export_school_branding --slug gilead-tech --out gilead.rmcbrand
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Export a school's branding (logo, colours, brand profile) to an encrypted .rmcbrand file."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug to export.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument("--out", required=True, help="Destination .rmcbrand path.")

    def handle(self, *args, **options):
        from apps.lifecycle.branding_portability import export_school_branding
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

        data = export_school_branding(school)
        out = Path(options["out"])
        out.write_bytes(data)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {school.slug} branding -> {out} ({len(data):,} bytes, encrypted + signed)."
            )
        )
