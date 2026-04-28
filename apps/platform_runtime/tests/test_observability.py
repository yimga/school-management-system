"""Structured observability helpers."""

from django.test import RequestFactory, TestCase

from apps.platform_runtime.observability import record_tenant_surface_view


class ObservabilityTests(TestCase):
    def test_record_tenant_surface_view_logs_dict(self):
        rf = RequestFactory()
        request = rf.get("/marketplace/catalog/")
        request.user = None
        request.school = None
        record_tenant_surface_view(
            surface="test_surface", request=request, extra={"k": 1}
        )
