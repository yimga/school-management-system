"""Tier 4: global Celery task platform events."""

from unittest.mock import patch

from django.test import SimpleTestCase


class CeleryTaskEventsTests(SimpleTestCase):
    def test_emit_celery_task_lifecycle_calls_emit_platform_event(self):
        from apps.platform_runtime.events import emit_celery_task_lifecycle

        with patch("apps.platform_runtime.events.emit_platform_event") as m:
            emit_celery_task_lifecycle(
                "started",
                "test.task",
                celery_task_id="tid-1",
                school_id="abc",
            )
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], "celery_task_started")

    def test_task_display_name(self):
        from apps.platform_runtime.celery_task_events import _task_display_name

        class _T:
            name = "apps.foo.bar"

        self.assertEqual(_task_display_name(_T()), "apps.foo.bar")
