"""Import graph health report + verify_tenant_import_closure script."""
from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.migration_cloud.closure_status import (
    build_import_graph_health_report,
    evaluate_import_closure_findings,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationArtifact, MigrationBundle
from apps.schools.models import School


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
    )


class ImportGraphHealthReportTests(TestCase):
    def test_layers_present_for_applied_bundle(self):
        school = _school("graph-health")
        bundle = MigrationBundle.objects.create(
            school=school,
            label="import",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"key-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            mapping_summary={"apply_totals": {"created": 1}},
        )
        report = build_import_graph_health_report(school, bundle=bundle)
        layers = report.get("import_graph_layers") or {}
        self.assertIn("detection", layers)
        self.assertIn("placement", layers)
        self.assertIn("teaching_graph", layers)
        self.assertIn("import_graph_ready", report)

    def test_needs_reimport_finding(self):
        school = _school("graph-reimport")
        bundle = MigrationBundle.objects.create(
            school=school,
            label="mis-tagged",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"key-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            discovery_summary={
                "per_artifact_domain": {"staff.xlsx": {"domain": "custom_fields"}},
            },
        )
        MigrationArtifact.objects.create(
            bundle=bundle,
            filename="staff.xlsx",
            path_within_bundle="staff.xlsx",
            assigned_domain="staff",
            sha256="a" * 64,
        )
        report = build_import_graph_health_report(school, bundle=bundle)
        findings = evaluate_import_closure_findings(report)
        self.assertTrue(any("re-import" in f.lower() for f in findings))


class VerifyTenantImportClosureScriptTests(TestCase):
    def test_script_imports_and_runs(self):
        import sys

        school = _school("verify-closure")
        old_argv = sys.argv
        try:
            sys.argv = [
                "verify_tenant_import_closure.py",
                "--school",
                school.slug,
            ]
            from scripts.verify_tenant_import_closure import main

            code = main()
        finally:
            sys.argv = old_argv
        self.assertEqual(code, 0)
