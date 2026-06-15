"""
Backfill default dashboard-pack assignments for existing schools.

Idempotent and per-school atomic. Dry-run by default; pass --apply to write.
Mirrors the promote_dyna_assignments.py backfill pattern. See
docs/DASHBOARD_PACKS_REVIVAL_PLAN.md (Phase 1).
"""

from django.core.management.base import BaseCommand
from django.db import DatabaseError, IntegrityError, transaction

from apps.siteconfig.dashboard_pack_resolver import assign_default_dashboard_packs


class Command(BaseCommand):
    help = (
        "Assign default dashboard packs (DashboardPackAssignment + "
        "TenantLayoutAssignment) per role for existing schools. Idempotent. "
        "Dry-run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write assignments (default is a dry run).",
        )
        parser.add_argument(
            "--tenant",
            dest="tenant",
            default="",
            help="Limit to one school by slug (optional).",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        apply = bool(options.get("apply"))
        tenant_slug = (options.get("tenant") or "").strip()

        qs = School.objects.all().order_by("name")
        if tenant_slug:
            qs = qs.filter(slug=tenant_slug)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No schools matched."))
            return

        packs_created = layouts_created = schools_touched = errors = 0
        for school in qs.iterator():
            try:
                with transaction.atomic():
                    summary = assign_default_dashboard_packs(school, apply=apply)
            except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(f"  {school.name}: {exc.__class__.__name__}: {exc}")
                )
                continue
            pc = summary.get("pack_assignments_created", 0)
            lc = summary.get("layout_assignments_created", 0)
            if pc or lc or summary.get("roles"):
                schools_touched += 1
            packs_created += pc
            layouts_created += lc
            if pc or lc:
                self.stdout.write(
                    f"  {school.name}: +{pc} pack, +{lc} layout"
                    + ("" if apply else " (dry-run)")
                )

        verb = "Applied" if apply else "Would apply"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb}: {schools_touched}/{total} schools, "
                f"{packs_created} pack + {layouts_created} layout assignments, "
                f"{errors} errors."
            )
        )
        if not apply:
            self.stdout.write("Re-run with --apply to write.")
