"""Middleware integration — tenant boundary pin follows request.tenant_ctx."""

from __future__ import annotations

import uuid

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.tenancy.boundary_core_guard import get_pinned_school_id
from apps.tenancy.context import TenantContext
from apps.tenancy.middleware_boundary_guard import TenantBoundaryCoreGuardMiddleware


def _echo_pin_view(request):
    return HttpResponse(get_pinned_school_id() or "")


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "apps.tenancy.middleware_boundary_guard.TenantBoundaryCoreGuardMiddleware",
    ],
)
class BoundaryGuardMiddlewareIntegrationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school_id = uuid.uuid4()

    def test_middleware_pins_school_id_during_request(self):
        middleware = TenantBoundaryCoreGuardMiddleware(_echo_pin_view)
        request = self.factory.get("/")
        request.tenant_ctx = TenantContext(
            tenant_id=str(self.school_id),
            schema_name=None,
            school_id=self.school_id,
            country=None,
            timezone=None,
            feature_flags={},
            policy_overrides={},
            host="demo.runmycampus.com",
        )
        response = middleware(request)
        self.assertEqual(response.content.decode(), str(self.school_id))
        self.assertIsNone(get_pinned_school_id())

    def test_middleware_unpins_after_request_even_on_empty_ctx(self):
        middleware = TenantBoundaryCoreGuardMiddleware(_echo_pin_view)
        request = self.factory.get("/")
        request.tenant_ctx = TenantContext.empty(host="runmycampus.com")
        response = middleware(request)
        self.assertEqual(response.content.decode(), "")
        self.assertIsNone(get_pinned_school_id())
