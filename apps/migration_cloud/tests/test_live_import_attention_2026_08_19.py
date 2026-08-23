"""Kickoff-page live import attention — counts, pipeline, no false-positive issues.

The Review & Import page (not Flight Deck) must show live created/updated/held
and must drop Repair / held badges once the *current* apply says quarantined=0.
Stale recon notes from a previous apply are not issues.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.live_import_attention import (
    bundle_needs_attention,
    compose_live_import,
    last_import_counts,
    pipeline_stages,
    post_apply_verification_complete,
    remediator_for,
)
from apps.migration_cloud.models import BundleStatus
from apps.migration_cloud.repair import repair_readiness, unresolved_issue_count
from apps.migration_cloud.tests.test_repair_2026_07_13 import FakeBundle, _quarantined
from apps.migration_cloud.views_tenant_upload import _progress_payload


class UnresolvedIssueHonestyTests(SimpleTestCase):
    def test_informational_recon_notes_are_not_issues(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping=_quarantined(0),
            recon={"notes": ["Scoped drill-down reconcile — read-only."]},
        )
        self.assertEqual(unresolved_issue_count(bundle), 0)
        self.assertFalse(repair_readiness(bundle).repairable)
        self.assertFalse(bundle_needs_attention(bundle))

    def test_stale_visible_notes_after_newer_apply_are_ignored(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "quarantined": 0,
                    "created": 105,
                    "updated": 0,
                    "applied_at": "2026-08-19T12:00:00+00:00",
                }
            },
            recon={
                "generated_at": "2026-08-19T11:00:00+00:00",
                "notes": ["students: only 40 row(s) are visible in the school"],
            },
        )
        self.assertEqual(unresolved_issue_count(bundle), 0)
        self.assertFalse(repair_readiness(bundle).repairable)
        self.assertFalse(bundle_needs_attention(bundle))
        live = compose_live_import(bundle, flight={"in_flight": False})
        self.assertFalse(live["issues_open"])
        self.assertEqual(live["held"], 0)
        self.assertIsNone(live["remediator"])

    def test_current_visible_drift_is_still_an_issue(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "quarantined": 0,
                    "created": 40,
                    "applied_at": "2026-08-19T11:00:00+00:00",
                }
            },
            recon={
                "generated_at": "2026-08-19T12:00:00+00:00",
                "notes": ["students: only 40 row(s) are visible in the school"],
            },
        )
        self.assertGreater(unresolved_issue_count(bundle), 0)
        self.assertTrue(repair_readiness(bundle).repairable)
        self.assertTrue(bundle_needs_attention(bundle))

    def test_held_rows_are_issues_and_leave_when_zero(self):
        held = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping=_quarantined(442),
        )
        self.assertEqual(unresolved_issue_count(held), 442)
        self.assertTrue(bundle_needs_attention(held))
        rem = remediator_for(held, issues=442, flight={})
        self.assertIsNotNone(rem)
        self.assertIn("held", rem["title"].lower())

        clean = FakeBundle(status=BundleStatus.APPLIED, mapping=_quarantined(0))
        self.assertEqual(unresolved_issue_count(clean), 0)
        self.assertFalse(bundle_needs_attention(clean))
        self.assertIsNone(remediator_for(clean, issues=0, flight={}))


class SchemaDriftRemediatorTests(SimpleTestCase):
    @mock.patch("apps.migration_cloud.tenant_schema_readiness.readiness_for_bundle")
    def test_schema_drift_hides_repair_button_even_when_stuck(self, readiness_for):
        from apps.migration_cloud.tenant_schema_readiness import TenantSchemaReadiness

        readiness_for.return_value = TenantSchemaReadiness(
            schema_name="tenant_gilead",
            ready=False,
            missing_labels=("academics_academicyear.is_soft_closed",),
        )
        bundle = FakeBundle(status=BundleStatus.APPLIED, mapping=_quarantined(442))
        rem = remediator_for(bundle, issues=442, flight={"stuck": True})
        self.assertIsNotNone(rem)
        self.assertFalse(rem["show_repair"])
        self.assertIn("Database update", rem["title"])

    @mock.patch("apps.migration_cloud.tenant_schema_readiness.readiness_for_bundle")
    def test_compose_live_import_labels_schema_blocked(self, readiness_for):
        from apps.migration_cloud.tenant_schema_readiness import TenantSchemaReadiness

        readiness_for.return_value = TenantSchemaReadiness(
            schema_name="tenant_gilead",
            ready=False,
            missing_labels=("people_studentprofile.search_index",),
        )
        bundle = FakeBundle(status=BundleStatus.APPLIED, mapping=_quarantined(442))
        live = compose_live_import(bundle, flight={"in_flight": False, "stuck": True})
        self.assertIn("Blocked", live["workflow_state"])
        self.assertIsNotNone(live["remediator"])
        self.assertFalse(live["remediator"]["show_repair"])


class LiveImportComposeTests(SimpleTestCase):
    def test_in_flight_uses_snapshot_live_totals(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLYING,
            mapping={"apply_totals": {"created": 0, "updated": 0, "quarantined": 442}},
        )
        snap = {
            "stages": [{"name": "APPLYING", "status": "current", "pct": 40}],
            "live_totals": {"created": 12, "updated": 8, "quarantined": 3},
        }
        live = compose_live_import(
            bundle,
            snapshot=snap,
            flight={"in_flight": True, "phase": "running", "stuck": False},
        )
        self.assertTrue(live["importing"])
        self.assertEqual((live["created"], live["updated"], live["held"]), (12, 8, 3))
        self.assertFalse(live["issues_open"])
        self.assertGreater(live["percent"], 0)
        import_stage = [s for s in live["pipeline"] if s["key"] == "import_school"][0]
        self.assertEqual(import_stage["visual"], "running")

    def test_settled_clean_apply_is_complete_not_attention(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "created": 5,
                    "updated": 105,
                    "quarantined": 0,
                    "dry_run": False,
                    "applied_at": "2026-08-19T12:00:00+00:00",
                }
            },
        )
        live = compose_live_import(bundle, flight={"in_flight": False})
        self.assertEqual(live["percent"], 100.0)
        self.assertEqual(live["held"], 0)
        self.assertFalse(live["issues_open"])
        self.assertFalse(live["needs_attention"])
        self.assertIsNone(live["remediator"])
        self.assertEqual(
            last_import_counts(bundle)["held"],
            0,
        )


class PipelineVerifyStageTests(SimpleTestCase):
    def _stage_visual(self, bundle, *, flight=None, issues=0):
        rows = pipeline_stages(bundle, flight=flight or {}, issues=issues)
        return {row["key"]: row["visual"] for row in rows}

    def test_applied_with_held_rows_marks_import_done_verify_failed(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "created": 100,
                    "updated": 0,
                    "quarantined": 12,
                    "dry_run": False,
                    "applied_at": "2026-08-22T12:00:00+00:00",
                }
            },
            recon={
                "generated_at": "2026-08-22T12:00:01+00:00",
                "per_domain": [{"domain": "students", "target_created": 100}],
            },
        )
        visual = self._stage_visual(bundle, issues=12)
        self.assertEqual(visual["import_school"], "done")
        self.assertEqual(visual["verify_school"], "failed")

    def test_applied_without_reconcile_shows_verify_running(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "created": 5,
                    "quarantined": 0,
                    "dry_run": False,
                    "applied_at": "2026-08-22T12:00:00+00:00",
                }
            },
            recon={},
        )
        self.assertFalse(post_apply_verification_complete(bundle))
        visual = self._stage_visual(bundle, issues=0)
        self.assertEqual(visual["import_school"], "done")
        self.assertEqual(visual["verify_school"], "running")

    def test_applied_after_reconcile_shows_verify_done(self):
        bundle = FakeBundle(
            status=BundleStatus.APPLIED,
            mapping={
                "apply_totals": {
                    "created": 5,
                    "quarantined": 0,
                    "dry_run": False,
                    "applied_at": "2026-08-22T12:00:00+00:00",
                }
            },
            recon={
                "generated_at": "2026-08-22T12:00:01+00:00",
                "per_domain": [{"domain": "students", "target_created": 5}],
            },
        )
        self.assertTrue(post_apply_verification_complete(bundle))
        visual = self._stage_visual(bundle, issues=0)
        self.assertEqual(visual["verify_school"], "done")


class ProgressPayloadLiveKeysTests(TestCase):
    @mock.patch("apps.migration_cloud.progress.refresh_snapshot")
    def test_payload_carries_live_board_keys(self, refresh):
        refresh.return_value = {"stages": [], "live_totals": {}}
        bundle = SimpleNamespace(
            pk=7,
            status=BundleStatus.APPLIED,
            get_status_display=lambda: "Applied",
            progress_snapshot={"stages": []},
            size_summary={},
            mapping_summary={
                "apply_totals": {
                    "created": 5,
                    "updated": 2,
                    "quarantined": 3,
                    "dry_run": False,
                }
            },
            reconciliation_summary={},
            artifacts=SimpleNamespace(all=lambda: []),
        )
        payload = _progress_payload(bundle)
        self.assertIn("percent", payload)
        self.assertIn("pipeline", payload)
        self.assertEqual(payload["held"], 3)
        self.assertTrue(payload["issues_open"])
        self.assertIsNotNone(payload["remediator"])
        self.assertFalse(payload["importing"])
        self.assertTrue(payload["done"])


class ReviewTemplateKickoffMarkers(SimpleTestCase):
    def test_review_page_hosts_live_board_not_flight_deck_only(self):
        from pathlib import Path

        review = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        wizard = Path("templates/migration_cloud/connector/_wizard_base.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-mc-live-board", review)
        self.assertIn("rmc-wfp-pipeline", review)
        self.assertIn("data-mc-live-remediator", review)
        self.assertIn("rmc-migration-live-import.js", wizard)
        self.assertIn("rmc_workflow_progress_canvas.html", review)
