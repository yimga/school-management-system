"""Print post-import closure readiness for one tenant.

Aggregates catalog inversion, teaching graph, people directory, finance ledger,
and (when resolvable) quarantine held-row counts — the same surfaces the
``remediate_tenant_post_import`` playbook repairs.

Usage::

    manage.py migration_closure_status --school gilead-tech
    manage.py migration_closure_status --school gilead-tech --json
    manage.py migration_closure_status --school gilead-tech --bundle-id 84
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.closure_status import build_migration_closure_report
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.quarantine_resolution import resolve_latest_bundle_for_school
from apps.migration_cloud.management.commands.remediate_teaching_graph_closure import (
    _tenant_schema,
)
from apps.schools.models import School


class Command(BaseCommand):
    help = (
        "Aggregate teaching graph, people directory, finance, catalog, and "
        "quarantine readiness for one school."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            required=True,
            help="School slug, subdomain, or pk (e.g. gilead-tech).",
        )
        parser.add_argument(
            "--bundle-id",
            type=int,
            default=None,
            help="Quarantine bundle id (defaults to newest for --school).",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        school = self._resolve_school(options["school"])
        bundle = self._resolve_bundle(school, options.get("bundle_id"))

        with _tenant_schema(school):
            report = build_migration_closure_report(school, bundle=bundle)

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write(f"School: {report['school']}")
        self.stdout.write(f"Playbook ready: {report['playbook_ready']}")

        catalog = report["catalog"]
        self.stdout.write(
            f"\nCatalog inversion actionable: {catalog['actionable']} "
            f"(phantom specialties={catalog['phantom_specialties']}, "
            f"departments={catalog['phantom_departments']})"
        )

        tg = report["teaching_graph"]
        self.stdout.write(
            f"\nTeaching graph — grades ready: {tg.get('ready_for_grades')}, "
            f"teacher portal: {tg.get('ready_for_teacher_portal')}, "
            f"students gradeable: {tg.get('students_with_class_and_specialty')}/"
            f"{tg.get('students_active')}"
        )

        people = report["people_directory"]
        self.stdout.write(
            f"\nPeople directory — enrollment SOT ready: "
            f"{people.get('ready_for_enrollment_sot')}, "
            f"active enrollments: {people.get('active_enrollments')}/"
            f"{people.get('students_active')}, "
            f"guardian links: {people.get('guardian_links')}"
        )

        fin = report["finance_ledger"]
        self.stdout.write(
            f"\nFinance ledger ready: {fin.get('ready')} "
            f"(draft with total={fin.get('draft_invoices_with_total')}, "
            f"issued without ledger={fin.get('issued_without_ledger')})"
        )

        q = report["quarantine"]
        if q.get("bundle_id"):
            self.stdout.write(
                f"\nQuarantine bundle {q['bundle_id']}: "
                f"{q.get('held_rows_pending', 0)} pending held row(s), "
                f"PDF noise candidates={q.get('pdf_noise_candidates', 0)}"
            )
        else:
            self.stdout.write("\nQuarantine: no bundle resolved for this school.")

    def _resolve_school(self, token: str) -> School:
        token = str(token or "").strip()
        if not token:
            raise CommandError("--school is required.")
        for lookup in (
            {"pk": token} if token.isdigit() else None,
            {"subdomain": token},
            {"slug": token},
        ):
            if lookup is None:
                continue
            school = School.objects.filter(**lookup).first()
            if school is not None:
                return school
        raise CommandError(f"School not found for {token!r}.")

    def _resolve_bundle(
        self, school: School, bundle_id: int | None
    ) -> MigrationBundle | None:
        if bundle_id is not None:
            return MigrationBundle.objects.filter(pk=bundle_id, school=school).first()
        slug = getattr(school, "slug", None) or getattr(school, "subdomain", None)
        if slug:
            return resolve_latest_bundle_for_school(str(slug))
        return None
