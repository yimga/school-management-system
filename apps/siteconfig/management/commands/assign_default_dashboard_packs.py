"""
Backfill default dashboard-pack assignments for existing schools.

Idempotent and per-school atomic. Dry-run by default; pass --apply to write.
Mirrors the promote_dyna_assignments.py backfill pattern. See
docs/DASHBOARD_PACKS_REVIVAL_PLAN.md (Phase 1).
"""

import json

from django.core.management.base import BaseCommand, CommandError
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
        parser.add_argument("--school-slug", default="", help="Limit to one school by slug.")
        parser.add_argument("--school-id", default="", help="Limit to one school by UUID/primary key.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicitly select the default no-write mode.",
        )
        parser.add_argument("--json", action="store_true", help="Emit structured JSON output.")

    def handle(self, *args, **options):
        from apps.schools.models import School

        if options.get("apply") and options.get("dry_run"):
            raise CommandError("Choose either --apply or --dry-run, not both.")
        apply = bool(options.get("apply"))
        tenant_slug = (options.get("school_slug") or options.get("tenant") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        as_json = bool(options.get("json"))
        if tenant_slug and school_id:
            raise CommandError("Choose either --school-id or --school-slug, not both.")

        qs = School.objects.all().order_by("name")
        if tenant_slug:
            qs = qs.filter(slug=tenant_slug)
        if school_id:
            qs = qs.filter(pk=school_id)

        total = qs.count()
        if total == 0:
            payload = {"applied": apply, "matched": 0, "errors": 0, "schools": []}
            if as_json:
                self.stdout.write(json.dumps(payload, sort_keys=True))
                return
            raise CommandError("No schools matched the requested scope.")

        packs_created = layouts_created = schools_touched = errors = 0
        school_results = []
        for school in qs.iterator():
            try:
                with transaction.atomic():
                    summary = assign_default_dashboard_packs(school, apply=apply)
            except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
                errors += 1
                school_results.append(
                    {"school_id": str(school.pk), "slug": school.slug, "error": exc.__class__.__name__}
                )
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
            school_results.append({**summary, "slug": school.slug})
            if apply:
                try:
                    from apps.compliance.models_audit import AuditLog

                    AuditLog.objects.create(
                        user=None,
                        action=AuditLog.Action.UPDATE,
                        model_name="SchoolRuntimeAssignments",
                        object_id=str(school.pk),
                        object_repr=f"Runtime assignment reconciliation for {school.slug}",
                        sensitivity=AuditLog.Sensitivity.MEDIUM,
                        app_label="siteconfig",
                        new_values={
                            "pack_assignments_created": pc,
                            "layout_assignments_created": lc,
                        },
                        changed_fields=["dashboard_pack_assignments", "dashboard_layout_assignments"],
                        reason="Idempotent tenant runtime assignment reconciliation",
                    )
                except (DatabaseError, IntegrityError, ImportError, TypeError, ValueError):
                    pass
            if pc or lc:
                self.stdout.write(
                    f"  {school.name}: +{pc} pack, +{lc} layout"
                    + ("" if apply else " (dry-run)")
                )

        payload = {
            "applied": apply,
            "matched": total,
            "schools_touched": schools_touched,
            "pack_assignments_created": packs_created,
            "layout_assignments_created": layouts_created,
            "errors": errors,
            "schools": school_results,
        }
        if as_json:
            self.stdout.write(json.dumps(payload, sort_keys=True, default=str))
            return

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
