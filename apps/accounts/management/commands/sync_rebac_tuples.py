"""Backfill relationship tuples from membership / guardian / role graphs."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.rebac_sync import backfill_school


class Command(BaseCommand):
    help = "Emit Postgres ReBAC tuples for one or all schools (batch 1507)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Single school primary key; omit for all active schools.",
        )
        parser.add_argument(
            "--limit-users",
            type=int,
            default=None,
            help="Cap per-school user permission rebuild (smoke tests).",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        school_id = options.get("school_id")
        limit_users = options.get("limit_users")
        if school_id:
            schools = School.objects.filter(pk=school_id)
        else:
            schools = School.objects.filter(is_active=True)
        total = {"memberships": 0, "guardians": 0, "teacher_assignments": 0, "users": 0}
        for school in schools.iterator():
            stats = backfill_school(school, limit_users=limit_users)
            for k, v in stats.items():
                total[k] = total.get(k, 0) + v
            self.stdout.write(
                self.style.SUCCESS(
                    f"school={school.pk} slug={school.slug} stats={stats}",
                ),
            )
        self.stdout.write(self.style.SUCCESS(f"done totals={total}"))
