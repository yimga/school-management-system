from __future__ import annotations

"""
Audit school ownership: report any school that has memberships but no owner.

Every school should carry at least one ``SchoolMembership.is_school_owner=True``
(the tenant's super-admin). The creator is seeded as owner on signup and the
0074 data migration backfills existing schools, so an ownerless-but-populated
school signals a data drift worth surfacing.

Usage:

    python manage.py audit_school_owners            # read-only report
    python manage.py audit_school_owners --repair   # assign a founding owner

``--repair`` mirrors the migration heuristic: the earliest ADMIN membership (or,
if none, the earliest membership of any role) becomes the owner. Schools with
zero memberships are reported but never auto-repaired — there is no member to
promote, so they need human attention.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Report (or repair) schools that have members but no owner."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Assign a founding owner (earliest ADMIN, else earliest member).",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School, SchoolMembership

        repair = bool(options.get("repair"))

        # Schools that have at least one membership but zero owners.
        ownerless = (
            School.objects.annotate(
                member_count=Count("memberships"),
                owner_count=Count(
                    "memberships", filter=Q(memberships__is_school_owner=True)
                ),
            )
            .filter(member_count__gt=0, owner_count=0)
            .order_by("name")
        )

        total = ownerless.count()
        if total == 0:
            self.stdout.write(
                self.style.SUCCESS("All populated schools have at least one owner.")
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"{total} school(s) have members but no owner:"
            )
        )

        repaired = 0
        for school in ownerless:
            base = SchoolMembership.objects.filter(school=school)
            founder = (
                base.filter(role="ADMIN").order_by("created_at", "pk").first()
                or base.order_by("created_at", "pk").first()
            )
            founder_label = (
                f"user_id={founder.user_id} (role={founder.role})"
                if founder
                else "no members"
            )
            self.stdout.write(
                f"  - {school.slug or school.pk}: candidate {founder_label}"
            )
            if repair and founder is not None:
                with transaction.atomic():
                    base.filter(pk=founder.pk).update(is_school_owner=True)
                repaired += 1
                logger.info(
                    "audit_school_owners.repaired school=%s owner_member=%s",
                    school.pk,
                    founder.pk,
                )

        if repair:
            self.stdout.write(
                self.style.SUCCESS(f"Repaired {repaired} school(s).")
            )
        else:
            self.stdout.write(
                "Run with --repair to assign a founding owner to each."
            )
