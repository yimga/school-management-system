"""AccessLog middleware GET sampling."""

from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.compliance.middleware import (
    AuditLoggingMiddleware,
    _should_persist_access_log,
)


class AccessLogSamplingTest(SimpleTestCase):
    def test_always_logs_mutations(self):
        request = RequestFactory().post("/finance/invoices/")
        response = HttpResponse(status=200)
        self.assertTrue(_should_persist_access_log(request, response))

    def test_always_logs_errors(self):
        request = RequestFactory().get("/backend/")
        response = HttpResponse(status=500)
        self.assertTrue(_should_persist_access_log(request, response))

    @override_settings(COMPLIANCE_ACCESS_LOG_GET_SAMPLE_RATE=0.0)
    def test_skips_sampled_get_when_rate_zero(self):
        request = RequestFactory().get("/backend/")
        response = HttpResponse(status=200)
        self.assertFalse(_should_persist_access_log(request, response))

    @override_settings(
        COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES=True,
        COMPLIANCE_ACCESS_LOG_GET_SAMPLE_RATE=0.0,
    )
    @patch("apps.compliance.middleware.AccessLog.objects.create")
    def test_middleware_honors_zero_sample_rate(self, create_mock):
        mw = AuditLoggingMiddleware(lambda r: HttpResponse("ok"))
        request = RequestFactory().get("/backend/")
        mw.process_response(request, HttpResponse("ok"))
        create_mock.assert_not_called()
