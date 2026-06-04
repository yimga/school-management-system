"""Workflow progress SSE tenant ingress guard (batch 1615)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.platform_runtime.views_workflow_progress import stream_view

User = get_user_model()


class WorkflowSSETenantGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="workflow_sse_guard",
            password="Test1234",
            role="TEACHER",
        )

    def test_tenant_host_without_school_returns_403(self):
        rf = RequestFactory()
        request = rf.get("/platform/workflow/progress/stream/")
        request.user = self.user
        request.public_host_kind = "tenant"
        request.school = None
        request.tenant = None
        response = stream_view(request)
        self.assertEqual(response.status_code, 403)
