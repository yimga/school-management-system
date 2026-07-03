"""Reconcile the passport dual-rail (transfer design §8 defect 1).

Two disconnected link mechanisms accumulated:
  * ``StudentPassportMembership`` rows (written by passport_services)
  * the ``StudentProfile.passport`` FK (read by the API timeline view)

This command converges both directions:
  1. memberships whose profile FK is still NULL  → set the FK
  2. profiles with a passport FK but no membership row → create the membership

Dry-run by default; ``--apply`` writes. Passports themselves stay lazy —
this never mints new passports, it only reconciles existing links.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.people.models import StudentProfile
from apps.people.student_passport_models import StudentPassportMembership


class Command(BaseCommand):
    help = "Reconcile StudentPassportMembership rows with the StudentProfile.passport FK (both directions)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the reconciled links (default is a dry-run report).",
        )
        parser.add_argument(
            "--school",
            type=str,
            default="",
            help="Limit to one school id (default: all schools).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        school_id = (options.get("school") or "").strip()

        memberships = StudentPassportMembership.objects.filter(  # tenant-isolation-allow: operator-backfill-command-platform-scope-optional-school-filter
            student_profile__passport__isnull=True
        ).select_related("student_profile", "passport")
        if school_id:
            memberships = memberships.filter(school_id=school_id)

        fk_linked = 0
        for membership in memberships.iterator():
            profile = membership.student_profile
            if profile is None or profile.passport_id is not None:
                continue
            fk_linked += 1
            if apply_changes:
                profile.passport_id = membership.passport_id
                profile.save(update_fields=["passport"])

        profiles = StudentProfile.objects.filter(  # tenant-isolation-allow: operator-backfill-command-platform-scope-optional-school-filter
            passport__isnull=False
        ).select_related("passport", "school")
        if school_id:
            profiles = profiles.filter(school_id=school_id)

        memberships_created = 0
        for profile in profiles.iterator():
            exists = StudentPassportMembership.objects.filter(
                passport_id=profile.passport_id,
                school_id=profile.school_id,
                student_profile_id=profile.pk,
            ).exists()
            if exists:
                continue
            memberships_created += 1
            if apply_changes:
                StudentPassportMembership.objects.create(
                    passport_id=profile.passport_id,
                    school_id=profile.school_id,
                    student_profile=profile,
                    consent_status=StudentPassportMembership.ConsentStatus.PRIVATE,
                    role="",
                )

        mode = "APPLIED" if apply_changes else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] passport dual-rail reconcile: "
                f"{fk_linked} profile FK link(s), "
                f"{memberships_created} membership row(s)."
            )
        )
