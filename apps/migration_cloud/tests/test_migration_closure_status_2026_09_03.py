"""Migration closure status aggregator + operator command."""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.migration_cloud.closure_status import build_migration_closure_report
from apps.migration_cloud.models import IntakeMethod, MigrationBundle
from apps.schools.models import School


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
    )


class MigrationClosureReportTests(TestCase):
    def test_build_report_includes_core_sections(self):
        school = _school("closure")
        report = build_migration_closure_report(school)
        self.assertEqual(report["school"], school.slug)
        self.assertIn("catalog", report)
        self.assertIn("teaching_graph", report)
        self.assertIn("people_directory", report)
        self.assertIn("finance_ledger", report)
        self.assertIn("playbook_ready", report)

    def test_quarantine_section_when_bundle_present(self):
        school = _school("closure-q")
        bundle = MigrationBundle.objects.create(
            school=school,
            label="import",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"key-{uuid.uuid4().hex}",
        )
        report = build_migration_closure_report(school, bundle=bundle)
        self.assertEqual(report["quarantine"]["bundle_id"], bundle.pk)


class MigrationClosureStatusCommandTests(TestCase):
    def test_command_loads_for_school(self):
        school = _school("closure-cmd")
        out = StringIO()
        call_command("migration_closure_status", school=school.slug, stdout=out)
        text = out.getvalue()
        self.assertIn("Playbook ready:", text)
        self.assertIn(school.slug, text)


class PeopleDirectoryReadinessBuilderTests(TestCase):
    def test_builds_for_applied_bundle(self):
        from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
        from apps.migration_cloud.views_tenant_upload import _build_people_directory_readiness

        school = _school("review-people")
        bundle = MigrationBundle.objects.create(
            school=school,
            label="applied",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"key-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            mapping_summary={"apply_totals": {"created": 1}},
        )
        readiness = _build_people_directory_readiness(bundle)
        self.assertIsNotNone(readiness)
        self.assertIn("students_active", readiness)

    def test_hidden_for_dry_run(self):
        from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
        from apps.migration_cloud.views_tenant_upload import _build_people_directory_readiness

        school = _school("review-dry")
        bundle = MigrationBundle.objects.create(
            school=school,
            label="dry",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"key-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            mapping_summary={"apply_totals": {"dry_run": True}},
        )
        self.assertIsNone(_build_people_directory_readiness(bundle))
