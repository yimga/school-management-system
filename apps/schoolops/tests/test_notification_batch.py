"""Salesforce pillar: notification sweep batching."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.schoolops.notification_batch import enqueue_in_chunks


class NotificationBatchTests(SimpleTestCase):
    def test_enqueue_respects_cap(self):
        task = MagicMock()
        ids = list(range(600))
        summary = enqueue_in_chunks(task, ids, max_total=10, chunk_size=3)
        self.assertEqual(summary["enqueued"], 10)
        self.assertEqual(summary["skipped_cap"], 590)
        self.assertEqual(task.delay.call_count, 10)
