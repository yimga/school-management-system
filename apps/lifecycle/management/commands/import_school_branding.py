"""Import a school's branding from a .rmcbrand file onto this (box-side) deployment.

Applies the logo + colours + brand profile so a self-hosted / offline box looks like
the school. The logo is made renderable with NO internet: it is stored DB-resident as
a data URI (branding.py resolves that first), and the raw bytes are also written into
the box MEDIA_ROOT with logo_url set to a box-relative /media/… path — replacing the
old non-resolving https://{slug}.school.lan/… URL.

    python manage.py import_school_branding --in gilead.rmcbrand --slug gilead-tech
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import a school's branding (logo, colours, brand profile) from a .rmcbrand file."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", required=True, help="Source .rmcbrand path.")
        parser.add_argument("--slug", default="", help="Box-side school slug to apply branding to.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument(
            "--no-media", action="store_true",
            help="Skip writing the logo file to MEDIA_ROOT (rely only on the DB-resident data URI).",
        )

    def handle(self, *args, **options):
        from apps.lifecycle.branding_portability import import_school_branding
        from apps.schools.models import School

        in_path = Path(options["in_path"])
        if not in_path.exists():
            raise CommandError(f"Bundle not found: {in_path}")

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id for the box-side school.")

        school = (
            School.objects.filter(slug=slug).first()
            if slug
            else School.objects.filter(pk=school_id).first()
        )
        if school is None:
            raise CommandError(f"School not found ({slug or school_id}).")

        try:
            result = import_school_branding(
                in_path.read_bytes(), school=school, write_media=not options["no_media"]
            )
        except ValueError as exc:
            # Signature / format failures are fail-closed and reported honestly.
            raise CommandError(f"Branding import rejected: {exc}") from exc

        offline = "yes" if result.get("logo_offline_ok") else "no"
        media = ", ".join(result.get("media_written") or []) or "(none)"
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported branding onto {school.slug}: "
                f"logo renders offline={offline}; media written={media}; "
                f"brand profile restored={result.get('brand_profile_restored')}."
            )
        )
        if not result.get("logo_offline_ok"):
            self.stdout.write(self.style.WARNING(
                "No offline logo present in the bundle — the source school had no logo, "
                "or its bytes were unreadable at export. Upload one on the box, or re-export."
            ))
