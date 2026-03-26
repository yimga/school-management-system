"""Tier 4: global Celery task platform events."""

import os
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

    @patch("apps.platform_runtime.tasks.call_command")
    def test_backlog_unlock_eval_passes_fail_on_sla_breach_from_env(self, m_cmd):
        from apps.platform_runtime.tasks import backlog_unlock_eval_and_cache

        with patch.dict(os.environ, {"BACKLOG_UNLOCK_FAIL_ON_SLA_BREACH": "1"}, clear=False):
            backlog_unlock_eval_and_cache()
        m_cmd.assert_called_once()
        _args, kwargs = m_cmd.call_args
        self.assertTrue(kwargs.get("fail_on_sla_breach"))

    @patch("apps.platform_runtime.tasks.call_command")
    def test_backlog_unlock_eval_default_no_sla_fail(self, m_cmd):
        from apps.platform_runtime.tasks import backlog_unlock_eval_and_cache

        with patch.dict(os.environ, {"BACKLOG_UNLOCK_FAIL_ON_SLA_BREACH": ""}, clear=False):
            backlog_unlock_eval_and_cache()
        _args, kwargs = m_cmd.call_args
        self.assertFalse(kwargs.get("fail_on_sla_breach"))
