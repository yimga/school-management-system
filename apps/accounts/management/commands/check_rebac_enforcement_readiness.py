"""
Pre-flight before enabling ``RMC_REBAC_ENFORCE_SENSITIVE``.

Reports, per tenant, every user who holds a sensitive capability via colon RBAC
but is missing the matching ReBAC ``can`` tuple — the exact users who would be
denied on flip. Exits non-zero if ANY checked tenant is not ready, so it can gate
a deploy step. Run ``sync_rebac_tuples`` first to build/refresh tuples, then run
this to prove parity before setting the enforcement env var.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.rebac_readiness import enforcement_readiness


class Command(BaseCommand):
    help = "Verify ReBAC tuple parity per tenant before enabling sensitive enforcement."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Single school primary key; omit for all active schools.",
        )
        parser.add_argument(
            "--user-limit",
            type=int,
            default=None,
            help="Cap members checked per school (smoke tests).",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        school_id = options.get("school_id")
        user_limit = options.get("user_limit")
        if school_id:
            schools = School.objects.filter(pk=school_id)
        else:
            schools = School.objects.filter(is_active=True)

        not_ready = 0
        total_gaps = 0
        for school in schools.iterator():
            report = enforcement_readiness(school, user_limit=user_limit)
            if report.ready:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"READY school={school.pk} slug={school.slug} "
                        f"users={report.checked_users} gaps=0",
                    ),
                )
                continue
            not_ready += 1
            total_gaps += len(report.would_be_denied)
            self.stdout.write(
                self.style.ERROR(
                    f"NOT-READY school={school.pk} slug={school.slug} "
                    f"users={report.checked_users} gaps={len(report.would_be_denied)}",
                ),
            )
            for gap in report.would_be_denied:
                self.stdout.write(f"    would-deny user_id={gap.user_id} code={gap.code}")

        if not_ready:
            self.stdout.write(
                self.style.ERROR(
                    f"enforcement pre-flight FAILED: {not_ready} tenant(s) not ready, "
                    f"{total_gaps} would-be-denied grant(s). "
                    f"Run sync_rebac_tuples, then re-check before enabling enforcement.",
                ),
            )
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("enforcement pre-flight PASSED for all checked tenants"))
