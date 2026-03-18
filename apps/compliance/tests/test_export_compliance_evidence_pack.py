import json
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.compliance.models import ComplianceAuditLog, RegionFeatureCompliance
from apps.compliance.models_audit import AccessLog, AuditLog, UserActivitySession
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


@override_settings(
    DATA_RETENTION={
        "audit_log_days": 30,
        "access_log_days": 30,
        "session_days": 30,
        "report_days": 365,
    }
)
class ExportComplianceEvidencePackTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
                "grading_scale": "0-100",
                "default_currency": "USD",
            },
        )
        self.actor = User.objects.create_user(
            username="evidence_actor",
            email="actor@example.com",
            password="Test1234!",
            role="ADMIN",
        )
        self.school = School.objects.create(
            name="Evidence School",
            slug="evidence-school",
            subdomain="evidence-school",
            is_active=True,
            default_region=self.region,
            settings={
                "tenant_policy_pack": {"code": "US", "version": "2026.1"},
                "tenant_config_metadata": {
                    "privacy_framework": {
                        "source": "region_pack:US",
                        "auto_applied": True,
                        "tenant_editable": False,
                        "compliance_locked": True,
                        "requires_approval": True,
                    }
                },
            },
        )

        RegionFeatureCompliance.objects.create(
            region=self.region,
            feature_code="Export_All_Student_Data",
            status=RegionFeatureCompliance.Status.ENABLED,
        )
        ComplianceAuditLog.objects.create(
            region=self.region,
            action_type="policy_enforced",
            description="GDPR Art. 20 portability export generated for student_id=11",
            details={
                "school_id": str(self.school.pk),
                "student_id": "11",
                "gdpr_action": "art20_portability_export",
            },
            user=self.actor,
            severity="high",
        )

        audit = AuditLog.objects.create(
            user=self.actor,
            action=AuditLog.Action.EXPORT,
            model_name="StudentProfile",
            object_id="11",
            object_repr="Student 11",
            app_label="people",
            reason="DSAR export",
        )
        AuditLog.objects.filter(pk=audit.pk).update(
            timestamp=timezone.now() - timedelta(days=90),
        )
        access = AccessLog.objects.create(
            user=self.actor,
            access_type=AccessLog.AccessType.API,
            resource="/compliance/gdpr/export/",
            status=AccessLog.Status.SUCCESS,
            request_method="GET",
            ip_address="127.0.0.1",
        )
        AccessLog.objects.filter(pk=access.pk).update(
            timestamp=timezone.now() - timedelta(days=90),
        )
        session = UserActivitySession.objects.create(
            user=self.actor,
            session_key="evidence-session-key",
            ip_address="127.0.0.1",
        )
        UserActivitySession.objects.filter(pk=session.pk).update(
            login_timestamp=timezone.now() - timedelta(days=90),
        )

    def test_exports_bundle_with_expected_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="evidence-pack-test-") as temp_dir:
            output_path = Path(temp_dir) / "pack.zip"
            call_command(
                "export_compliance_evidence_pack",
                "--region",
                "USA",
                "--school-slug",
                "evidence-school",
                "--output-file",
                str(output_path),
            )

            self.assertTrue(output_path.exists())
            with zipfile.ZipFile(output_path, "r") as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("compliance_scorecard.json", names)
                self.assertIn("dsar_events.json", names)
                self.assertIn("policy_locks.json", names)
                self.assertIn("retention_snapshot.json", names)
                self.assertIn("region_feature_rules.csv", names)
                self.assertIn("README.txt", names)

                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest["region_filter"], "USA")
                self.assertEqual(manifest["school_slug_filter"], "evidence-school")
                self.assertEqual(manifest["counts"]["schools"], 1)
                self.assertEqual(manifest["counts"]["dsar_events"], 1)

                dsar_events = json.loads(
                    archive.read("dsar_events.json").decode("utf-8")
                )
                self.assertEqual(len(dsar_events), 1)
                self.assertEqual(
                    dsar_events[0]["gdpr_action"], "art20_portability_export"
                )

                policy_locks = json.loads(
                    archive.read("policy_locks.json").decode("utf-8")
                )
                self.assertEqual(len(policy_locks), 1)
                self.assertIn(
                    "privacy_framework", policy_locks[0]["compliance_locked_keys"]
                )
                self.assertIn(
                    "privacy_framework", policy_locks[0]["requires_approval_keys"]
                )

                retention = json.loads(
                    archive.read("retention_snapshot.json").decode("utf-8")
                )
                self.assertGreaterEqual(
                    retention["datasets"]["audit_logs"]["records_past_retention"],
                    1,
                )
                self.assertGreaterEqual(
                    retention["datasets"]["access_logs"]["records_past_retention"],
                    1,
                )
                self.assertGreaterEqual(
                    retention["datasets"]["sessions"]["records_past_retention"],
                    1,
                )

    def test_raises_for_unknown_school_filter(self):
        with self.assertRaises(CommandError):
            call_command(
                "export_compliance_evidence_pack",
                "--region",
                "USA",
                "--school-slug",
                "missing-school",
            )
