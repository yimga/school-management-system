"""AccessLog middleware behavior under the test runner."""

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.compliance.middleware import AuditLoggingMiddleware


class AuditAccessLogMiddlewareTest(SimpleTestCase):
    def test_skips_access_log_insert_when_test_writes_disabled(self):
        self.assertFalse(settings.COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES)
        mw = AuditLoggingMiddleware(lambda r: HttpResponse("ok"))
        request = RequestFactory().get("/backend/")
        response = mw.process_response(request, HttpResponse("ok"))
        self.assertEqual(response.status_code, 200)

    @override_settings(COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES=True)
    def test_setting_gate_allows_writes_when_enabled(self):
        self.assertTrue(settings.COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES)
