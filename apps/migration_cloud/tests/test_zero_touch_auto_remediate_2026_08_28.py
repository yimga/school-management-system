"""Zero-touch import closure — spec step 3 (2026-08-28)."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.auto_remediate import (
    auto_remediate_after_apply,
    import_closure_banner,
    sync_reconciliation_closure,
)
from apps.migration_cloud.landers._helpers import (
    enrich_missing_required_row,
    row_is_pdf_noise_hold,
    row_is_unstructured_text_fragment,
)
from apps.migration_cloud.models import ReconciliationClosureStatus
from apps.migration_cloud.quarantine_profile import profile_quarantine_distribution


class SchoolStatsFragmentTests(SimpleTestCase):
    def test_school_stats_metadata_without_raw_line_is_fragment(self):
        row = {"page": "2", "line": "14", "custom_fields": {"table": "summary"}}
        self.assertTrue(
            row_is_unstructured_text_fragment(row, artifact="school_stats_2026-01-18.pdf")
        )
        self.assertTrue(
            row_is_pdf_noise_hold("academics", row, "school_stats_2026-01-18.pdf")
        )

    def test_school_stats_with_subject_is_not_noise(self):
        row = {"subject_name": "Biology", "page": "1"}
        self.assertFalse(
            row_is_pdf_noise_hold("academics", row, "school_stats_2026-01-18.pdf")
        )


class EnrichMissingRequiredTests(SimpleTestCase):
    def test_academics_code_fills_name(self):
        row = {"subject_code": "MATH101"}
        enriched, evidence = enrich_missing_required_row("academics", row)
        self.assertEqual(enriched["subject_name"], "MATH101")
        self.assertIn("subject_name←subject_code", evidence)

    def test_no_evidence_when_nothing_to_derive(self):
        row = {"page": "1"}
        _, evidence = enrich_missing_required_row("academics", row)
        self.assertEqual(evidence, [])


class ImportClosureBannerTests(SimpleTestCase):
    def test_banner_when_auto_resolved_and_closed(self):
        bundle = mock.Mock()
        bundle.reconciliation_status = ReconciliationClosureStatus.CLOSED
        bundle.mapping_summary = {
            "auto_remediation": {
                "auto_resolved_total": 88,
                "pdf_noise_dismissed": 88,
                "fragment_dismissed": 0,
            }
        }
        with mock.patch(
            "apps.migration_cloud.auto_remediate.pending_quarantine_count",
            return_value=0,
        ):
            banner = import_closure_banner(bundle)
        self.assertIsNotNone(banner)
        self.assertIn("88", banner["headline"])
        self.assertIn("auto-resolved", banner["headline"].lower())

    def test_no_banner_when_pending_remains(self):
        bundle = mock.Mock()
        bundle.reconciliation_status = ReconciliationClosureStatus.PENDING_HUMAN
        bundle.mapping_summary = {"auto_remediation": {"auto_resolved_total": 10}}
        with mock.patch(
            "apps.migration_cloud.auto_remediate.pending_quarantine_count",
            return_value=3,
        ):
            self.assertIsNone(import_closure_banner(bundle))


class AutoRemediateAfterApplyIntegrationTests(TestCase):
    def test_after_apply_sets_closed_when_queue_empty(self):
        from apps.automation.models import MigrationQuarantineRecord
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.create(
            idempotency_key="zero-touch-closure-test",
            label="closure test",
        )
        bundle.mapping_summary = {"apply_totals": {"quarantined": 88}}
        bundle.save(update_fields=["mapping_summary"])

        with mock.patch(
            "apps.migration_cloud.auto_remediate.auto_remediate_before_repair",
            return_value={
                "informational_dismissed": 0,
                "pdf_noise_dismissed": 88,
                "fragment_dismissed": 0,
                "pending_before": 88,
            },
        ), mock.patch(
            "apps.migration_cloud.auto_remediate.auto_replay_invalid_ref_holds",
            return_value={"replayed": 0, "failed": 0, "errors": []},
        ), mock.patch(
            "apps.migration_cloud.auto_remediate.auto_enrich_and_replay_missing_required",
            return_value={"enriched": 0, "replayed": 0, "skipped": 0, "errors": []},
        ), mock.patch(
            "apps.migration_cloud.auto_remediate.auto_dismiss_pdf_noise_holds",
            return_value={"dismissed": 0},
        ), mock.patch(
            "apps.migration_cloud.auto_remediate.auto_dismiss_unstructured_fragments",
            return_value={"dismissed": 0},
        ), mock.patch(
            "apps.migration_cloud.auto_remediate.pending_quarantine_count",
            side_effect=[88, 0, 0],
        ):
            result = auto_remediate_after_apply(bundle)

        bundle.refresh_from_db()
        self.assertEqual(result["auto_resolved_total"], 88)
        self.assertEqual(bundle.reconciliation_status, ReconciliationClosureStatus.CLOSED)
        self.assertEqual(
            (bundle.mapping_summary or {}).get("auto_remediation", {}).get(
                "auto_resolved_total"
            ),
            88,
        )
        # No phantom pending records left
        self.assertEqual(
            MigrationQuarantineRecord.objects.filter(
                status=MigrationQuarantineRecord.Status.PENDING
            ).count(),
            0,
        )


class ProfileDistributionTests(SimpleTestCase):
    def test_profile_structure(self):
        bundle = mock.Mock(pk=84)
        record = mock.Mock()
        record.issue_class = "missing_required"
        record.domain = "academics"
        record.payload = {
            "artifact": "school_stats_2026.pdf",
            "source_row": {"page": "1"},
        }
        qs = mock.Mock()
        qs.iterator.return_value = iter([record])
        with mock.patch(
            "apps.migration_cloud.quarantine_profile.quarantine_queryset_for_bundle",
            return_value=qs,
        ), mock.patch(
            "apps.migration_cloud.landers._helpers.row_is_pdf_noise_hold",
            return_value=True,
        ):
            profile = profile_quarantine_distribution(bundle)
        self.assertEqual(profile["total"], 1)
        self.assertEqual(profile["pdf_noise_candidates"], 1)
        self.assertEqual(profile["by_issue_class"]["missing_required"], 1)
