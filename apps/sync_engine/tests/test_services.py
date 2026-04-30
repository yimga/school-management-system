"""Sync engine: pending rows, visibility, retries, apply_remote conflicts."""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.api.mobile_api import MobileDevice, OfflineSyncQueue
from apps.sync_engine import services


class SyncEngineServicesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sync_engine_user",
            password="x",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id=uuid.uuid4(),
            device_name="d",
            platform="WEB",
            app_version="1.0",
        )

    def test_get_visible_sync_state_counts_statuses(self):
        OfflineSyncQueue.objects.create(
            device=self.device,
            entity_type="attendance",
            entity_id=0,
            action="CREATE",
            data={},
            client_timestamp=timezone.now(),
            status="FAILED",
        )
        OfflineSyncQueue.objects.create(
            device=self.device,
            entity_type="attendance",
            entity_id=0,
            action="CREATE",
            data={},
            client_timestamp=timezone.now(),
            status="COMPLETED",
        )
        state = services.get_visible_sync_state(self.user.id)
        self.assertEqual(state["failed"], 1)
        self.assertEqual(state["completed"], 1)

    def test_retry_failed_sync_items_resets_status(self):
        q = OfflineSyncQueue.objects.create(
            device=self.device,
            entity_type="attendance",
            entity_id=0,
            action="CREATE",
            data={},
            client_timestamp=timezone.now(),
            status="FAILED",
            retry_count=0,
        )
        out = services.retry_failed_sync_items(self.user.id, max_retries=3)
        self.assertEqual(out["retried"], 1)
        q.refresh_from_db()
        self.assertEqual(q.status, "PENDING")
        self.assertEqual(q.retry_count, 1)

    def test_apply_remote_detects_duplicate_entity_ops(self):
        res = services.apply_remote(
            1,
            self.user.id,
            [
                {"entity": "grade", "id": "5"},
                {"entity": "grade", "id": "5"},
            ],
        )
        self.assertEqual(res["applied"], 1)
        self.assertEqual(len(res["conflicts"]), 1)
