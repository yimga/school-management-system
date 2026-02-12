"""
Verify that RLS (Row-Level Security) is enabled on tenant-scoped tables (PostgreSQL only).
Usage: python manage.py verify_tenant_rls

Use after deployment to PostgreSQL to confirm tenant isolation is active.
On SQLite/MySQL the command exits with OK and a note that RLS is N/A.
"""
from django.core.management.base import BaseCommand
from django.db import connection

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
                self.style.WARNING("RLS is only used on PostgreSQL. Current backend: %s. Skipping check." % connection.vendor)
            )
            return
        with connection.cursor() as cursor:
            # Resolve table names to oid and check relrowsecurity (RLS enabled)
            placeholders = ",".join(["%s"] * len(TENANT_RLS_TABLES))
            cursor.execute(
                """
                SELECT c.relname, c.relrowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                AND c.relname IN (%s)
                """ % placeholders,
                TENANT_RLS_TABLES,
            )
            rows = {row[0]: row[1] for row in cursor.fetchall()}
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
                self.stdout.write(self.style.WARNING("  ⚠ %s table not found (migration not applied?)" % t))
        if disabled or missing:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR("Verify tenant RLS: FAILED (%s disabled, %s missing)" % (len(disabled), len(missing)))
            )
            return
        self.stdout.write(self.style.SUCCESS("Verify tenant RLS: OK (%s tables)" % len(ok)))
