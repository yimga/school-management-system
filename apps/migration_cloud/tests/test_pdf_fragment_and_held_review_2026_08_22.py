"""PDF text fragments + held-review page body (2026-08-22)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.automation.models import MigrationQuarantineRecord
from apps.migration_cloud.landers._helpers import row_is_unstructured_text_fragment
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School
from apps.platform_runtime.northstar_self_heal_status import self_heal_requires_attention


class PdfFragmentDetectionTests(SimpleTestCase):
    def test_custom_fields_raw_line_is_fragment(self):
        row = {"custom_fields": {"raw_line": "School Performance Summary"}}
        self.assertTrue(row_is_unstructured_text_fragment(row))

    def test_subject_name_is_not_fragment(self):
        row = {"custom_fields": {"raw_line": "x"}, "subject_name": "Mathematics"}
        self.assertFalse(row_is_unstructured_text_fragment(row))


class AcademicsLanderFragmentSkipTests(SimpleTestCase):
    def test_pdf_fragment_is_skipped_not_quarantined(self):
        from unittest.mock import MagicMock

        lander = AcademicsLander()
        ctx = LanderContext(
            school=MagicMock(pk=1),
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=True,
        )
        result = lander.land(
            canonical_rows=iter(
                [{"custom_fields": {"raw_line": "Best Worst Class Stats"}}]
            ),
            ctx=ctx,
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(len(result.errors), 0)


class SelfHealAttentionTests(SimpleTestCase):
    def test_self_healed_pass_does_not_require_attention(self):
        report = {"status": "SELF_HEALED_PASS", "unsafe_ticket_paths": []}
        self.assertFalse(self_heal_requires_attention(report))

    def test_unsafe_tickets_require_attention(self):
        report = {"status": "SELF_HEALED_PASS", "unsafe_ticket_paths": ["tickets/x.md"]}
        self.assertTrue(self_heal_requires_attention(report))


class HeldReviewTemplateBlockTests(SimpleTestCase):
    def test_held_review_view_does_not_force_wizard_base(self):
        source = Path("apps/migration_cloud/views_tenant_upload.py").read_text(
            encoding="utf-8"
        )
        start = source.index("class TenantMigrationHeldReviewView")
        end = source.index("class TenantMigrationQuarantineExportView", start)
        block = source[start:end]
        self.assertNotIn('_wizard_base.html"', block)


class FounderDashboardLayoutTests(SimpleTestCase):
    def test_page_header_precedes_cockpit_widgets(self):
        source = Path("templates/super/founder_dashboard.html").read_text(encoding="utf-8")
        header_pos = source.index("rmc-page-header-glow")
        pulse_pos = source.index('founder__platform_pulse')
        self.assertLess(header_pos, pulse_pos)

    def test_customer_success_header_precedes_cockpit_widgets(self):
        source = Path("templates/customersuccess/super_dashboard.html").read_text(
            encoding="utf-8"
        )
        header_pos = source.index('include "studio_os/components/page_header.html"')
        pulse_pos = source.index("cs_super__platform_pulse")
        self.assertLess(header_pos, pulse_pos)


class WizardBaseBlockBridgeTests(SimpleTestCase):
    def test_wizard_base_bridges_cp_shell_page_into_connector_body(self):
        source = Path(
            "templates/migration_cloud/connector/_wizard_base.html"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "{% block connector_body %}{% block cp_shell_page %}{% endblock %}{% endblock %}",
            source,
        )


class AutoDismissFragmentIntegrationTests(TestCase):
    def setUp(self):
        from apps.automation.models import MigrationRun

        self.school = School.objects.create(name="Frag School", subdomain="frag-school")
        self.bundle = MigrationBundle.objects.create(
            label="frag-bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="frag-bundle",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )
        MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="academics",
            row_index=1,
            issue_class="missing_required",
            payload={
                "error": "academics: missing subject_name/code",
                "source_row": {"custom_fields": {"raw_line": "School Performance"}},
            },
        )

    def test_auto_dismiss_clears_pdf_fragments(self):
        from apps.migration_cloud.auto_remediate import auto_dismiss_unstructured_fragments
        from apps.migration_cloud.quarantine_resolution import pending_quarantine_count

        stats = auto_dismiss_unstructured_fragments(self.bundle)
        self.assertEqual(stats["dismissed"], 1)
        self.assertEqual(pending_quarantine_count(self.bundle), 0)
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                school=self.school, status=MigrationQuarantineRecord.Status.REPAIRED
            ).count(),
            1,
        )
