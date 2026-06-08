from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError
from django.http import HttpResponse
from django.test import SimpleTestCase

from apps.schools.middleware import (
    TenantMiddleware,
    _reset_rls_school_id_if_set,
)
from apps.tenancy.middleware_rls_jwt import RLSJWTBindingMiddleware


class RLSConnectionQuarantineTests(SimpleTestCase):
    def test_tenant_response_quarantines_connection_when_reset_fails(self):
        request = SimpleNamespace(_rls_school_id_set=True)
        middleware = TenantMiddleware(lambda _request: HttpResponse())
        with (
            patch(
                "apps.schools.rls_context.reset_rls_school_id",
                side_effect=DatabaseError("response reset failed"),
            ),
            patch(
                "apps.schools.rls_context.quarantine_rls_connection"
            ) as quarantine,
        ):
            response = middleware.process_response(request, HttpResponse())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(request._rls_school_id_set)
        quarantine.assert_called_once_with("response reset failed")

    def test_exception_finally_quarantines_connection_when_reset_fails(self):
        request = SimpleNamespace(_rls_school_id_set=True)
        with (
            patch(
                "apps.schools.rls_context.reset_rls_school_id",
                side_effect=DatabaseError("finally reset failed"),
            ),
            patch(
                "apps.schools.rls_context.quarantine_rls_connection"
            ) as quarantine,
        ):
            _reset_rls_school_id_if_set(request)

        self.assertFalse(request._rls_school_id_set)
        quarantine.assert_called_once_with("finally reset failed")

    def test_rls_jwt_quarantines_connection_when_reset_fails(self):
        request = SimpleNamespace(
            META={},
            COOKIES={},
            path="/api/test",
            school=None,
            user=SimpleNamespace(is_authenticated=False),
            get_host=lambda: "tenant.example.com",
        )
        middleware = RLSJWTBindingMiddleware(lambda _request: HttpResponse())
        middleware._enabled = True
        with (
            patch(
                "apps.tenancy.middleware_rls_jwt._extract_token",
                return_value="signed",
            ),
            patch(
                "apps.tenancy.middleware_rls_jwt._verify_jwt",
                return_value={"school_id": "00000000-0000-0000-0000-000000000001"},
            ),
            patch("apps.tenancy.middleware_rls_jwt.set_rls_school_id"),
            patch(
                "apps.tenancy.middleware_rls_jwt.reset_rls_school_id",
                side_effect=DatabaseError("jwt reset failed"),
            ),
            patch(
                "apps.schools.rls_context.quarantine_rls_connection"
            ) as quarantine,
        ):
            response = middleware(request)

        self.assertEqual(response.status_code, 200)
        quarantine.assert_called_once_with("jwt reset failed")
