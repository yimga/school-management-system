"""Async transfer APPLYING→APPLIED continue path (off-HTTP MC pipeline)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.people.models_transfer import TransferCase
from apps.people.transfer_service import (
    continue_transfer_case_if_ready,
    run_transfer_case,
)
from apps.schools.models import School


class TransferOffHttpEnqueueTests(SimpleTestCase):
    def test_ingest_off_http_flag_passed_from_run_default(self):
        """Production run_transfer_case defaults off_http=True into intake."""
        # Signature lock — default must stay True so HTTP never sync-applies.
        import inspect

        from apps.people.transfer_service import run_transfer_case as rtc

        params = inspect.signature(rtc).parameters
        self.assertTrue(params["off_http"].default)


class TransferContinueWhenBundleReadyTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Cont Src", slug="cont-src", subdomain="cont-src"
        )
        self.target = School.objects.create(
            name="Cont Tgt", slug="cont-tgt", subdomain="cont-tgt"
        )
        self.case = TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk="00000000-0000-0000-0000-000000000001",
            status=TransferCase.Status.APPLYING,
            target_bundle_id=99,
            history=[],
        )

    def test_continue_waits_while_bundle_pending(self):
        from apps.migration_cloud.models import BundleStatus

        bundle = MagicMock()
        bundle.status = BundleStatus.MAPPED
        with patch(
            "apps.migration_cloud.models.MigrationBundle.objects.filter"
        ) as filt:
            filt.return_value.first.return_value = bundle
            out = continue_transfer_case_if_ready(self.case)
        self.assertFalse(out.get("advanced"))
        self.assertEqual(out.get("reason"), "bundle_pending")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.APPLYING)
