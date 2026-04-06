"""
Verify that RLS (Row-Level Security) is enabled on tenant-scoped tables (PostgreSQL only).
Usage: python manage.py verify_tenant_rls

Use after deployment to PostgreSQL to confirm tenant isolation is active.
On SQLite/MySQL the command exits with OK and a note that RLS is N/A.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.schools.repositories.rls_repository import get_tenant_rls_status

# Tables that should have RLS enabled (from people, academics, finance, evals, reports, siteconfig, schools migrations)
TENANT_RLS_TABLES = [
    "schools_schoolmembership",
    "people_teacherprofile",
    "people_studentprofile",
    "academics_academicyear",
    "academics_term",
    "academics_department",
    "academics_specialty",
    "academics_classroom",
    "academics_classroompromotionmapping",
    "academics_subject",
    "academics_subjectassignment",
    "academics_attendance",
    "academics_incident",
    "academics_certificationexamsession",
    "academics_certificationdocumentchecklist",
    "academics_certificationexampreset",
    "academics_certificationfeetemplate",
    "academics_classbooklist",
    "academics_curriculumstandard",
    "finance_feeplan",
    "finance_invoice",
    "finance_payment",
    "evals_assessmentweights",
    "evals_teacherassignment",
    "evals_evaluation",
    "reports_reportcard",
    "siteconfig_officialreporttemplate",
    "siteconfig_featuretogglestate",
]


class Command(BaseCommand):
    help = "Verify RLS is enabled on tenant tables (PostgreSQL only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print summary; no per-table output.",
        )

    def handle(self, *args, **options):
        quiet = options.get("quiet", False)
        if connection.vendor != "postgresql":
            self.stdout.write(
                self.style.WARNING(
                    "RLS is only used on PostgreSQL. Current backend: %s. Skipping check."
                    % connection.vendor
                )
            )
            return
        if getattr(settings, "USE_DJANGO_TENANTS", False):
            self.stdout.write(
                self.style.WARNING(
                    "RLS is not used when USE_DJANGO_TENANTS=True. "
                    "Schema-per-tenant isolation is active. Skipping check."
                )
            )
            return
        rows = get_tenant_rls_status(TENANT_RLS_TABLES)
        missing = []
        disabled = []
        ok = []
        for table in TENANT_RLS_TABLES:
            if table not in rows:
                missing.append(table)
            elif not rows[table]:
                disabled.append(table)
            else:
                ok.append(table)
        if not quiet:
            for t in ok:
                self.stdout.write(self.style.SUCCESS("  ✓ %s RLS enabled" % t))
            for t in disabled:
                self.stdout.write(self.style.ERROR("  ✗ %s RLS disabled" % t))
            for t in missing:
                self.stdout.write(
                    self.style.WARNING(
                        "  ⚠ %s table not found (migration not applied?)" % t
                    )
                )
        if disabled or missing:
            message = "Verify tenant RLS: FAILED (%s disabled, %s missing)" % (
                len(disabled),
                len(missing),
            )
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(message))
            raise CommandError(message)
        self.stdout.write(
            self.style.SUCCESS("Verify tenant RLS: OK (%s tables)" % len(ok))
        )
