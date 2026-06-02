"""Workflow Progress 10x — waves 2–4 contract tests."""

from __future__ import annotations

import json

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.platform_runtime.workflow_autopilot import policy_allows_auto_fix, promotion_hint
from apps.platform_runtime.workflow_degrading import is_degrading, resolve_display_status
from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind
from apps.platform_runtime.workflow_registry import TAG_TENANT_SAFE, WORKFLOWS
from apps.platform_runtime.workflow_sla import slo_seconds_for_key
from apps.platform_runtime.workflow_tenant_trust import is_tenant_safe_workflow_key


class WorkflowDegradingTests(SimpleTestCase):
    def test_past_expected_is_degrading_not_stuck(self):
        from datetime import timedelta

        from django.utils import timezone

        run = type(
            "Run",
            (),
            {
                "status": "running",
                "expected_duration_seconds": 10,
                "last_heartbeat_at": timezone.now() - timedelta(seconds=12),
                "started_at": timezone.now() - timedelta(seconds=12),
                "workflow_key": "test",
            },
        )()
        self.assertTrue(is_degrading(run))
        self.assertEqual(resolve_display_status(run), "degrading")


class WorkflowSlaRegistryTests(SimpleTestCase):
    def test_provision_has_slo(self):
        self.assertGreater(slo_seconds_for_key("tenant_school_provision"), 0)


class WorkflowTenantTrustTests(SimpleTestCase):
    def test_evals_bulk_grades_is_tenant_safe(self):
        self.assertTrue(is_tenant_safe_workflow_key("evals_bulk_grades"))
        self.assertIn(TAG_TENANT_SAFE, WORKFLOWS["evals_bulk_grades"].default_tags)


class WorkflowFixHandlerTests(TestCase):
    def test_retry_kind_returns_ok_shape(self):
        from apps.platform_runtime.models import WorkflowRun

        run = WorkflowRun.objects.create(workflow_key="workflow_progress_e2e_demo")
        result = apply_auto_fix_kind(run=run, kind="retry_once_with_backoff")
        self.assertTrue(result.get("ok"))

    def test_preview_does_not_mutate_run_status(self):
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import preview_auto_fix_kind

        run = WorkflowRun.objects.create(
            workflow_key="workflow_progress_e2e_demo",
            status="failed",
        )
        preview = preview_auto_fix_kind(run=run, kind="retry_once_with_backoff")
        run.refresh_from_db()
        self.assertTrue(preview.get("dry_run"))
        self.assertEqual(run.status, "failed")


class WorkflowSlaNotifyTests(TestCase):
    def test_sla_breach_publishes_event_once(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        from apps.platform_runtime.models import WorkflowRun, WorkflowSlaBreach
        from apps.platform_runtime.workflow_sla import maybe_record_sla_breach

        run = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            status="running",
            started_at=timezone.now() - timedelta(seconds=900),
        )
        with patch(
            "apps.platform_runtime.workflow_sla.publish_sla_breach_event"
        ) as publish:
            self.assertTrue(maybe_record_sla_breach(run=run, actual_seconds=900))
            publish.assert_called_once()
            self.assertFalse(
                maybe_record_sla_breach(run=run, actual_seconds=901),
            )
        self.assertEqual(WorkflowSlaBreach.objects.filter(run_id=run.pk).count(), 1)


class WorkflowFlightDeckHttpTests(SimpleTestCase):
    def test_flight_deck_json_anonymous_401(self):
        from apps.platform_runtime.views_workflow_flight_deck import flight_deck_json_view

        req = RequestFactory().get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
        )
        req.user = AnonymousUser()
        resp = flight_deck_json_view(req)
        self.assertEqual(resp.status_code, 401)


class WorkflowAutopilotPolicyTests(TestCase):
    def test_policy_allows_configured_kind(self):
        from apps.platform_runtime.models import WorkflowAutopilotPolicy

        WorkflowAutopilotPolicy.objects.create(
            workflow_key="tenant_school_provision",
            tenant_schema="",
            allowed_auto_fix_kinds=["retry_once_with_backoff"],
            enabled=True,
        )
        self.assertTrue(
            policy_allows_auto_fix(
                workflow_key="tenant_school_provision",
                auto_fix_kind="retry_once_with_backoff",
            )
        )

    def test_promotion_hint_after_three_applies(self):
        from apps.platform_runtime.models import WorkflowAutopilotApplyLog

        for _ in range(3):
            WorkflowAutopilotApplyLog.objects.create(
                run_id=1,
                workflow_key="evals_bulk_grades",
                auto_fix_kind="retry_once_with_backoff",
                outcome="applied",
            )
        hint = promotion_hint(
            workflow_key="evals_bulk_grades",
            auto_fix_kind="retry_once_with_backoff",
        )
        self.assertIsNotNone(hint)
        self.assertTrue(hint.get("promote_autopilot"))


class WorkflowControlPlaneNavTests(SimpleTestCase):
    def test_flight_deck_in_control_plane_nav(self):
        from django.contrib.auth import get_user_model

        from apps.schools.control_plane_nav import build_control_plane_nav

        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        request.user = get_user_model()(is_superuser=True, username="workflow_10x_nav")
        ids = [
            item.get("id")
            for section in build_control_plane_nav(request)
            for item in (section.get("items") or [])
            if isinstance(item, dict)
        ]
        self.assertIn("super_workflow_flight_deck", ids)


class WorkflowEnableAutopilotHttpTests(SimpleTestCase):
    def test_enable_autopilot_anonymous_401(self):
        from apps.platform_runtime.views_workflow_autopilot import enable_autopilot_view

        req = RequestFactory().post(
            "/platform-runtime/workflow-progress/autopilot/enable/",
            data=json.dumps({"workflow_key": "tenant_school_provision"}),
            content_type="application/json",
        )
        req.user = AnonymousUser()
        resp = enable_autopilot_view(req)
        self.assertEqual(resp.status_code, 401)
