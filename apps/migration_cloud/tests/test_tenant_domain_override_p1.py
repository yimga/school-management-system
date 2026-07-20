"""P1-Override — tenant domain corrections must remount classify/map."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationArtifact, MigrationBundle
from apps.migration_cloud.views_tenant_upload import _sync_tenant_domain_overrides


class SyncTenantDomainOverridesTests(TestCase):
    def setUp(self):
        self.bundle = MigrationBundle.objects.create(
            label="override test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"tenant-override-{self.id()}",
            status=BundleStatus.MAPPED,
            discovery_summary={"per_artifact_domain": {}},
            schema_name="public",
        )
        self.art = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="students.csv",
            filename="students.csv",
            byte_size=12,
            sha256="b" * 64,
            assigned_domain="staff",
        )

    def test_sync_writes_operator_map_and_rewinds_mapped(self):
        _sync_tenant_domain_overrides(self.bundle)
        self.bundle.refresh_from_db()
        op = (self.bundle.discovery_summary or {}).get("operator_assigned_domains") or {}
        self.assertEqual(op.get("students.csv"), "staff")
        self.assertEqual(self.bundle.status, BundleStatus.PROFILED)

    def test_build_jobs_prefers_artifact_assigned_domain(self):
        from apps.migration_cloud.orchestrator import _build_jobs

        self.bundle.discovery_summary = {
            "per_artifact_domain": {
                "students.csv": {"domain": "students", "method": "classifier"},
            }
        }
        self.bundle.mapping_summary = {
            "per_artifact": {"students.csv": [{"source": "a", "canonical": "external_id"}]},
        }
        self.bundle.save()
        jobs = _build_jobs(self.bundle)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].domain, "staff")


class SyncHelperSourceTests(SimpleTestCase):
    def test_helper_exported(self):
        from apps.migration_cloud import views_tenant_upload as v

        self.assertTrue(callable(v._sync_tenant_domain_overrides))
