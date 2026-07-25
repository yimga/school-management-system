"""Audit G-1a — self-serve intake → bundle → guarded-apply pipeline wiring.

These tests exercise the WIRING added in G-1a (services.intake_pipeline +
views_customer), controlling the bundle status directly so they are deterministic
and do not depend on the heavy profile/classify/map/apply pipeline succeeding on a
synthetic export. The heavy pipeline is existing, separately-tested code; here we
prove:

  * the reconciler walks the intake FSM to match its bundle's status,
  * it NEVER auto-crosses promotion-pending-approval → promotion-in-progress,
  * guardian consent blocks the school's approval,
  * approval enqueues the REAL apply on the durable outbox,
  * the self-serve upload creates + links a bundle and advances the FSM.
"""
from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class IntakePipelineG1aTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.schools.models import School

        cls.school = School.objects.create(
            name="Pipeline School",
            slug="g1a-pipeline-school",
            subdomain="g1a-pipeline-school",
        )
        cls.user = User.objects.create_user(
            username="g1a_user",
            email="g1a@example.invalid",
            password="not-a-real-password",
            role=User.Role.ADMIN,
        )
        try:
            from apps.schools.models import SchoolMembership

            SchoolMembership.objects.create(user=cls.user, school=cls.school, role="ADMIN")
        except Exception:  # noqa: BLE001
            pass

    # ---- helpers ----

    def _make_intake(self, state, **extra):
        from apps.migration_cloud.models_intake import MigrationIntakeRequest

        return MigrationIntakeRequest.objects.create(
            tenant=self.school,
            requested_by_user=self.user,
            vendor_slug="powerschool",
            state=state,
            **extra,
        )

    def _make_bundle(self, status, last_dry_run=None):
        from apps.migration_cloud.models import MigrationBundle

        return MigrationBundle.objects.create(
            school=self.school,
            schema_name="public",
            label="pipeline-test",
            idempotency_key=f"g1a-{uuid.uuid4()}",
            status=status,
            size_summary=({"last_dry_run": last_dry_run} if last_dry_run else {}),
        )

    # ---- reconciler walk ----

    def test_sync_walks_to_pending_approval_with_preview(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        bundle = self._make_bundle(BundleStatus.MAPPED, last_dry_run={"created": 12})
        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value, bundle=bundle)

        sync_intake_from_bundle(intake, actor=self.user)
        intake.refresh_from_db()
        self.assertEqual(
            intake.state, MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
        )

    def test_sync_never_auto_crosses_into_promotion(self):
        """Even when the bundle is APPLYING, an un-approved intake parks at pending."""
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        bundle = self._make_bundle(BundleStatus.APPLYING)
        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value, bundle=bundle)

        sync_intake_from_bundle(intake, actor=self.user)
        intake.refresh_from_db()
        self.assertEqual(
            intake.state, MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
        )

    def test_sync_completes_after_reconciled(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        bundle = self._make_bundle(BundleStatus.RECONCILED)
        # School already approved: intake sits in promotion-in-progress.
        intake = self._make_intake(
            MigrationIntakeState.PROMOTION_IN_PROGRESS.value, bundle=bundle
        )

        sync_intake_from_bundle(intake, actor=self.user)
        intake.refresh_from_db()
        self.assertEqual(intake.state, MigrationIntakeState.COMPLETE.value)

    def test_sync_marks_failed_on_bundle_failure(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        bundle = self._make_bundle(BundleStatus.FAILED)
        intake = self._make_intake(
            MigrationIntakeState.EXTRACTION_IN_PROGRESS.value, bundle=bundle
        )

        sync_intake_from_bundle(intake, actor=self.user)
        intake.refresh_from_db()
        self.assertEqual(intake.state, MigrationIntakeState.FAILED.value)

    def test_sync_noop_for_concierge_intake(self):
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value)  # no bundle
        self.assertIsNone(sync_intake_from_bundle(intake, actor=self.user))
        intake.refresh_from_db()
        self.assertEqual(intake.state, MigrationIntakeState.MAA_SIGNED.value)

    # ---- consent gate ----

    def test_consent_incomplete_blocks_walk_at_pending(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import sync_intake_from_bundle

        bundle = self._make_bundle(BundleStatus.MAPPED, last_dry_run={"created": 1})
        intake = self._make_intake(
            MigrationIntakeState.MAA_SIGNED.value,
            bundle=bundle,
            guardian_consent_required_count=3,
            guardian_consent_collected_count=1,
        )
        sync_intake_from_bundle(intake, actor=self.user)
        intake.refresh_from_db()
        # Consent gates promotion-pending-approval, so the walk parks one step short.
        self.assertEqual(
            intake.state, MigrationIntakeState.VALIDATION_COMPLETE.value
        )

    # ---- promotion enqueue ----

    def test_begin_promotion_enqueues_apply(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import begin_promotion
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        # PENDING bundle so any eager drain short-circuits (apply requires MAPPED).
        bundle = self._make_bundle(BundleStatus.PENDING)
        intake = self._make_intake(
            MigrationIntakeState.PROMOTION_IN_PROGRESS.value, bundle=bundle
        )
        begin_promotion(intake, actor=self.user)
        self.assertTrue(
            HeavyWorkOutbox.objects.filter(
                kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE, bundle_id=bundle.pk,
            ).exists()
        )

    def test_begin_promotion_noop_without_bundle(self):
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import begin_promotion

        intake = self._make_intake(MigrationIntakeState.PROMOTION_IN_PROGRESS.value)
        result = begin_promotion(intake, actor=self.user)
        self.assertFalse(result.get("queued"))

    # ---- approve view integration ----

    def test_approve_view_advances_and_enqueues(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        bundle = self._make_bundle(BundleStatus.PENDING)
        intake = self._make_intake(
            MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value, bundle=bundle
        )
        self.client.force_login(self.user)
        url = reverse(
            "migration_intake_customer:migration-intake-approve-promotion",
            kwargs={"id": str(intake.id)},
        )
        resp = self.client.post(url, {"confirm": "on"})
        self.assertEqual(resp.status_code, 302)
        intake.refresh_from_db()
        self.assertEqual(
            intake.state, MigrationIntakeState.PROMOTION_IN_PROGRESS.value
        )
        self.assertTrue(
            HeavyWorkOutbox.objects.filter(
                kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE, bundle_id=bundle.pk,
            ).exists()
        )

    def test_approve_view_blocked_by_consent(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState

        bundle = self._make_bundle(BundleStatus.PENDING)
        intake = self._make_intake(
            MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value,
            bundle=bundle,
            guardian_consent_required_count=2,
            guardian_consent_collected_count=0,
        )
        self.client.force_login(self.user)
        url = reverse(
            "migration_intake_customer:migration-intake-approve-promotion",
            kwargs={"id": str(intake.id)},
        )
        resp = self.client.post(url, {"confirm": "on"})
        self.assertEqual(resp.status_code, 400)
        intake.refresh_from_db()
        self.assertEqual(
            intake.state, MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
        )

    # ---- upload view integration ----

    def test_upload_creates_and_links_bundle(self):
        from unittest.mock import patch

        from apps.migration_cloud.models_intake import MigrationIntakeState

        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value)
        self.client.force_login(self.user)
        url = reverse(
            "migration_intake_customer:migration-intake-upload",
            kwargs={"id": str(intake.id)},
        )
        csv_bytes = b"student_external_id,first_name,last_name\nPS-1,Ada,Lovelace\n"
        upload = SimpleUploadedFile("students.csv", csv_bytes, content_type="text/csv")

        # Isolate the upload→ingest→link→advance wiring from the heavy pipeline.
        with patch(
            "apps.migration_cloud.services.connector_bundle_bridge.run_bundle_pipeline",
            return_value={"queued": True},
        ):
            resp = self.client.post(url, {"export_file": upload})
        self.assertEqual(resp.status_code, 302)
        intake.refresh_from_db()
        self.assertIsNotNone(intake.bundle_id)
        self.assertEqual(
            intake.state, MigrationIntakeState.EXTRACTION_IN_PROGRESS.value
        )

    def test_full_self_serve_flow_end_to_end(self):
        """Upload → guarded pipeline → approve → real apply → complete.

        No mocks on the pipeline: the real advance/apply/reconcile machinery runs.
        Production drains the durable outbox on a worker/beat; here we pump it
        explicitly with ``drain_heavy_work_outbox`` (and suppress the racy
        background-thread kick) so the flow is deterministic. Proves the wiring
        drives a bundle end-to-end and the intake FSM tracks its status.
        """
        from unittest.mock import patch

        from apps.migration_cloud.models import BundleStatus, MigrationBundle
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.platform_runtime.heavy_work_outbox import drain_heavy_work_outbox

        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value)
        self.client.force_login(self.user)
        up_url = reverse(
            "migration_intake_customer:migration-intake-upload",
            kwargs={"id": str(intake.id)},
        )
        status_url = reverse(
            "migration_intake_customer:migration-intake-status",
            kwargs={"id": str(intake.id)},
        )
        approve_url = reverse(
            "migration_intake_customer:migration-intake-approve-promotion",
            kwargs={"id": str(intake.id)},
        )
        csv_bytes = (
            b"student_external_id,first_name,last_name,grade_level\n"
            b"PS-100,Grace,Hopper,7\nPS-101,Ada,Lovelace,8\n"
        )
        upload = SimpleUploadedFile("students.csv", csv_bytes, content_type="text/csv")

        with patch("apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain"):
            # 1. Upload → bundle created + linked + FSM at extraction-in-progress.
            resp = self.client.post(up_url, {"export_file": upload})
            self.assertEqual(resp.status_code, 302)
            intake.refresh_from_db()
            self.assertIsNotNone(intake.bundle_id)

            # 2. Worker drains: advance → MAPPED + dry-run apply (preview, no writes).
            drain_heavy_work_outbox(limit=50)
            bundle = MigrationBundle.objects.get(pk=intake.bundle_id)
            self.assertEqual(bundle.status, BundleStatus.MAPPED)
            self.assertIn("last_dry_run", (bundle.size_summary or {}))

            # 3. Status load reconciles the intake FSM → awaiting the school's approval.
            self.client.get(status_url)
            intake.refresh_from_db()
            self.assertEqual(
                intake.state, MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
            )

            # 4. School approves → real apply enqueued; worker drains → apply + reconcile.
            resp = self.client.post(approve_url, {"confirm": "on"})
            self.assertEqual(resp.status_code, 302)
            drain_heavy_work_outbox(limit=50)
            bundle.refresh_from_db()
            self.assertIn(bundle.status, (BundleStatus.APPLIED, BundleStatus.RECONCILED))

            # 5. Final status load rolls the intake to its terminal state.
            self.client.get(status_url)
            intake.refresh_from_db()
            self.assertIn(
                intake.state,
                (
                    MigrationIntakeState.COMPLETE.value,
                    MigrationIntakeState.PROMOTION_IN_PROGRESS.value,
                ),
            )

    def test_upload_rejected_before_maa_signed(self):
        from apps.migration_cloud.models_intake import MigrationIntakeState

        intake = self._make_intake(MigrationIntakeState.MAA_PENDING_COUNSEL.value)
        self.client.force_login(self.user)
        url = reverse(
            "migration_intake_customer:migration-intake-upload",
            kwargs={"id": str(intake.id)},
        )
        # GET at the wrong state redirects to status (not an upload form).
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/status/", resp["Location"])

    def test_looks_like_csv_rejects_binary_with_delimiter(self):
        """The signature-less-text gate must reject binary that merely contains a
        delimiter — ``latin-1`` decodes anything, so decode-success is not proof."""
        from apps.migration_cloud.services.intake_pipeline import _looks_like_csv

        # Real CSV heads pass — plain ASCII and accented UTF-8.
        self.assertTrue(_looks_like_csv(b"a,b,c\n1,2,3\n"))
        self.assertTrue(_looks_like_csv("nom,prénom\nÉric,Ada\n".encode("utf-8")))
        # Binary bytes that happen to contain a comma are rejected (control ratio).
        self.assertFalse(
            _looks_like_csv(b"\x01\x02\x03\x04\x05,\x06\x07\x08\x0e\x0f")
        )
        # A NUL byte is always binary.
        self.assertFalse(_looks_like_csv(b"a,b\x00c,d"))

    @override_settings(MIGRATION_CLOUD_SELF_SERVE_APPLY_ENABLED=False)
    def test_kill_switch_closes_upload_surface(self):
        """Operator kill-switch off → upload GET/POST redirect, no bundle, service refuses."""
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import (
            IntakePipelineError,
            attach_and_start,
        )

        intake = self._make_intake(MigrationIntakeState.MAA_SIGNED.value)
        self.client.force_login(self.user)
        url = reverse(
            "migration_intake_customer:migration-intake-upload",
            kwargs={"id": str(intake.id)},
        )
        self.assertEqual(self.client.get(url).status_code, 302)
        csv = SimpleUploadedFile("s.csv", b"a,b\n1,2\n", content_type="text/csv")
        resp = self.client.post(url, {"export_file": csv})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/status/", resp["Location"])
        intake.refresh_from_db()
        self.assertIsNone(intake.bundle_id)
        # Defense in depth: the service layer refuses even a direct call.
        with self.assertRaises(IntakePipelineError):
            attach_and_start(intake, csv, actor=self.user)

    @override_settings(MIGRATION_CLOUD_SELF_SERVE_APPLY_ENABLED=False)
    def test_kill_switch_blocks_promotion(self):
        """Kill-switch off → begin_promotion refuses and the approve view does not advance."""
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.models_intake import MigrationIntakeState
        from apps.migration_cloud.services.intake_pipeline import begin_promotion

        bundle = self._make_bundle(BundleStatus.MAPPED, last_dry_run={"total": 1})
        intake = self._make_intake(
            MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value, bundle=bundle,
        )
        self.assertEqual(begin_promotion(intake, actor=self.user)["reason"], "disabled")

        self.client.force_login(self.user)
        approve_url = reverse(
            "migration_intake_customer:migration-intake-approve-promotion",
            kwargs={"id": str(intake.id)},
        )
        resp = self.client.post(approve_url, {"confirm": "on"})
        self.assertEqual(resp.status_code, 302)
        intake.refresh_from_db()
        self.assertEqual(
            intake.state, MigrationIntakeState.PROMOTION_PENDING_APPROVAL.value
        )
