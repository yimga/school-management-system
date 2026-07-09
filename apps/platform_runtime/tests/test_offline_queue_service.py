"""Server offline queue: enqueue, process, idempotency, tenant scope, conflict resolution."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    get_merged_sync_bar_state,
    process_offline_queue,
    resolve_conflict_choice,
    retry_failed_actions,
)
from apps.schools.models import School


class OfflineQueueCoreTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Off A",
            slug="off-a",
            subdomain="off-a",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Off B",
            slug="off-b",
            subdomain="off-b",
            is_active=True,
        )
        cls.user = User.objects.create_user(username="off_u1", password="x" * 8)
        cls.user_2 = User.objects.create_user(username="off_u2", password="x" * 8)

    def test_enqueue_creates_row(self):
        row = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "hello", "title": "t"},
            idempotency_key="",
        )
        self.assertEqual(row.school_id, self.school_a.id)
        self.assertEqual(row.status, OfflineAction.Status.QUEUED)

    def test_idempotency_same_key(self):
        key = "idem-" + str(uuid.uuid4())
        r1 = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "a"},
            idempotency_key=key,
        )
        r2 = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "b"},
            idempotency_key=key,
        )
        self.assertEqual(r1.pk, r2.pk)

    def test_idempotency_same_school_different_user_matches_constraint(self):
        key = "idem-school-" + str(uuid.uuid4())
        r1 = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "a"},
            idempotency_key=key,
        )
        r2 = enqueue_offline_action(
            user_id=self.user_2.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "b"},
            idempotency_key=key,
        )
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(
            OfflineAction.objects.filter(
                school_id=self.school_a.id,
                idempotency_key=key,
            ).count(),
            1,
        )

    def test_process_notes_report_syncs(self):
        enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "offline note body text"},
            idempotency_key="",
        )
        summary = process_offline_queue(school_id=self.school_a.id, user_id=self.user.id)
        self.assertGreaterEqual(summary["synced"], 1)
        row = OfflineAction.objects.filter(
            school_id=self.school_a.id, user_id=self.user.id
        ).latest("created_at")
        self.assertEqual(row.status, OfflineAction.Status.SYNCED)

    def test_retry_failed_actions(self):
        row = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "x"},
            idempotency_key="",
        )
        OfflineAction.objects.filter(pk=row.pk).update(status=OfflineAction.Status.FAILED)
        n = retry_failed_actions(school_id=self.school_a.id, user_id=self.user.id)
        self.assertGreaterEqual(n, 1)
        row.refresh_from_db()
        self.assertEqual(row.status, OfflineAction.Status.QUEUED)

    def test_conflict_resolution_use_latest(self):
        row = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "x"},
            idempotency_key="",
        )
        OfflineAction.objects.filter(pk=row.pk).update(
            status=OfflineAction.Status.CONFLICT,
            conflict_reason="test conflict",
        )
        out = resolve_conflict_choice(
            action_id=row.pk,
            school_id=self.school_a.id,
            user_id=self.user.id,
            choice=OfflineAction.Resolution.USE_LATEST,
        )
        self.assertTrue(out.get("ok"))
        row.refresh_from_db()
        self.assertEqual(row.status, OfflineAction.Status.SYNCED)

    def test_tenant_isolation_merge_counts(self):
        enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "a"},
            idempotency_key="",
        )
        sa = get_merged_sync_bar_state(self.user.id, self.school_a.id)
        sb = get_merged_sync_bar_state(self.user.id, self.school_b.id)
        self.assertGreaterEqual(sa.get("offline_action_pending", 0), 1)
        self.assertGreaterEqual(sa["pending"], sb["pending"])

    def test_resolve_wrong_school_fails(self):
        row = enqueue_offline_action(
            user_id=self.user.id,
            school_id=self.school_a.id,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "x"},
            idempotency_key="",
        )
        OfflineAction.objects.filter(pk=row.pk).update(
            status=OfflineAction.Status.CONFLICT,
        )
        out = resolve_conflict_choice(
            action_id=row.pk,
            school_id=self.school_b.id,
            user_id=self.user.id,
            choice=OfflineAction.Resolution.USE_LATEST,
        )
        self.assertFalse(out.get("ok"))
