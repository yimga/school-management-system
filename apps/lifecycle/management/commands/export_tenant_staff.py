"""Export a school's teacher logins + profiles to an encrypted+signed .rmcstaff file.

Run this on the CLOUD. It exists because neither documented path carries staff onto a
sovereign box: delta sync refuses a teacher CREATE (409 ``insert_held_for_entity``), and
``export_tenant_bundle`` ships ``people.teacherprofile`` WITHOUT the ``accounts.User``
rows it points at, so ``import_tenant_bundle`` rolls the whole tenant import back on the
dangling FK. See ``apps/lifecycle/staff_portability.py`` and
``docs/EDGE_SYNC_IDENTITY_HOLD.md``.

    python manage.py export_tenant_staff --slug gilead-tech --out gilead.rmcstaff

The file carries password hashes and is encrypted + signed for that one school. Move it
like a credential, and delete it once imported.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Export a school's teacher logins + profiles to an encrypted .rmcstaff file."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug to export.")
        parser.add_argument(
            "--school-id",
            dest="school_id",
            default="",
            help="School UUID (alternative to --slug).",
        )
        parser.add_argument("--out", required=True, help="Destination .rmcstaff path.")

    def handle(self, *args, **options):
        from apps.lifecycle.staff_portability import export_staff_bundle
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

        data = export_staff_bundle(school)
        out = Path(options["out"])
        out.write_bytes(data)

        from apps.people.models import TeacherProfile

        count = TeacherProfile.objects.filter(school=school).count()
        if not count:
            self.stdout.write(
                self.style.WARNING(
                    f"{school.slug} has no teacher profiles — the bundle is empty. "
                    "Nothing to move."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {count} teacher(s) for {school.slug} -> {out} "
                f"({len(data):,} bytes, encrypted + signed)."
            )
        )
        self.stdout.write(
            "  This file contains password hashes. Move it as a credential and delete it "
            "after import (or use --reset-passwords on the box side)."
        )
        self.stdout.write(
            f"  On the box:  python manage.py import_tenant_staff --in {out.name} "
            f"--expect-school-id {school.id}"
        )
