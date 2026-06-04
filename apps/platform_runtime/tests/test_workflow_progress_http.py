"""HTTP contract tests for Workflow Progress Bus (no live server)."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.workflow_request_middleware import _should_track_request


class WorkflowProgressMiddlewareContractTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_api_post_tracked_without_opt_in_header(self):
        req = self.rf.post("/api/v1/students/import/")
        req.user = type("U", (), {"is_authenticated": True, "id": 1})()
        self.assertTrue(_should_track_request(req))

    def test_super_form_post_requires_opt_in_header(self):
        req = self.rf.post("/super/siteconfig/some-form/")
        req.user = type("U", (), {"is_authenticated": True, "id": 1})()
        self.assertFalse(_should_track_request(req))
        req.META["HTTP_X_RMC_WORKFLOW_TRACK"] = "1"
        self.assertTrue(_should_track_request(req))

    def test_migration_bundle_apply_skipped_for_middleware(self):
        req = self.rf.post("/super/migration/api/v1/bundles/9/apply/")
        req.user = type("U", (), {"is_authenticated": True, "id": 1})()
        self.assertFalse(_should_track_request(req))


class WorkflowProgressActiveApiTests(SimpleTestCase):
    def test_active_runs_anonymous_401(self):
        from apps.platform_runtime.views_workflow_progress import active_runs_view

        req = RequestFactory().get(
            "/platform-runtime/workflow-progress/active/",
            HTTP_ACCEPT="application/json",
        )
        req.user = AnonymousUser()
        resp = active_runs_view(req)
        self.assertEqual(resp.status_code, 401)

    def test_stream_anonymous_401(self):
        from apps.platform_runtime.views_workflow_progress import stream_view

        req = RequestFactory().get(
            "/platform-runtime/workflow-progress/stream/",
            HTTP_ACCEPT="text/event-stream",
        )
        req.user = AnonymousUser()
        resp = stream_view(req)
        self.assertEqual(resp.status_code, 401)


class WorkflowProgressChipNoiseTests(SimpleTestCase):
    def test_young_generic_celery_hidden_from_chip(self):
        from django.utils import timezone

        from apps.platform_runtime.workflow_tracker import _visible_in_progress_chip

        run = type(
            "Run",
            (),
            {
                "workflow_key": "celery.quick_sweep",
                "current_step_ordinal": 1,
                "started_at": timezone.now(),
            },
        )()
        self.assertFalse(_visible_in_progress_chip(run))

    def test_named_workflow_visible_immediately(self):
        from django.utils import timezone

        from apps.platform_runtime.workflow_tracker import _visible_in_progress_chip

        run = type(
            "Run",
            (),
            {
                "workflow_key": "migration_bundle_apply",
                "current_step_ordinal": 1,
                "started_at": timezone.now(),
            },
        )()
        self.assertTrue(_visible_in_progress_chip(run))


class WorkflowProgressE2eDemoTests(SimpleTestCase):
    def test_e2e_demo_anonymous_401(self):
        from apps.platform_runtime.views_workflow_progress import e2e_demo_start_view

        req = RequestFactory().post(
            "/platform-runtime/workflow-progress/e2e-demo/start/",
            HTTP_ACCEPT="application/json",
        )
        req.user = AnonymousUser()
        resp = e2e_demo_start_view(req)
        self.assertEqual(resp.status_code, 401)
