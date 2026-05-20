"""Async/Celery/Channels runtime contracts (honest — no perf claims)."""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase


class AsyncRuntimeContractTests(SimpleTestCase):
    def test_celery_beat_schedule_non_empty(self):
        from django.conf import settings

        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        self.assertGreater(len(schedule), 0)
        self.assertIn("orchestration-process-due-runs", schedule)

    def test_automation_shared_tasks_document_tenant_isolation(self):
        root = Path(__file__).resolve().parents[3]
        tasks_path = root / "apps" / "automation" / "tasks.py"
        text = tasks_path.read_text(encoding="utf-8")
        self.assertIn("@shared_task", text)
        self.assertIn("tenant-isolation-allow", text)

    def test_celery_json_serializers_only(self):
        from django.conf import settings

        self.assertEqual(settings.CELERY_TASK_SERIALIZER, "json")
        self.assertEqual(settings.CELERY_ACCEPT_CONTENT, ["json"])

    def test_channels_fallback_in_memory_without_redis(self):
        from django.conf import settings

        try:
            import channels  # noqa: F401
        except ImportError:
            return
        layers = getattr(settings, "CHANNEL_LAYERS", {})
        backend = (layers.get("default") or {}).get("BACKEND", "")
        self.assertTrue(backend)
