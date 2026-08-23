from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from apps.compliance.middleware import IPCountryAccessMiddleware


@override_settings(
    ENABLE_IP_COUNTRY_ACCESS_CONTROL=True,
    BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS=True,
)
class IPCountryAccessMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = IPCountryAccessMiddleware(lambda request: None)

    @patch("apps.compliance.middleware.check_request_access")
    def test_root_path_is_probe_safe(self, check_request_access):
        request = self.factory.get("/")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        check_request_access.assert_not_called()

    @patch("apps.compliance.middleware.check_request_access")
    def test_authentication_routes_are_probe_safe(self, check_request_access):
        request = self.factory.get("/authentication/login/")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        check_request_access.assert_not_called()

    @patch("apps.compliance.middleware.check_request_access")
    def test_ready_endpoint_is_probe_safe(self, check_request_access):
        request = self.factory.get("/ready/")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        check_request_access.assert_not_called()

    # The AccessLog INSERT this asserts is switched OFF under RUNNING_TESTS
    # (one row per response amplifies SQLite lock contention). config/settings.py
    # says to opt in when exercising the audit middleware explicitly, which is
    # exactly what this test does.
    @override_settings(COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES=True)
    @patch("apps.compliance.middleware.log_access_denial")
    @patch("apps.compliance.middleware.AccessLog.objects.create")
    @patch("apps.compliance.middleware.check_request_access")
    def test_non_bypass_route_is_enforced(
        self, check_request_access, accesslog_create, _log_access_denial
    ):
        check_request_access.return_value = (False, "Denied for test")
        request = self.factory.get("/reports/")
        request.META["REMOTE_ADDR"] = "203.0.113.10"

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        check_request_access.assert_called_once()
        accesslog_create.assert_called_once()

    @override_settings(COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES=False)
    @patch("apps.compliance.middleware.AccessLog.objects.create")
    @patch("apps.compliance.middleware.check_request_access")
    def test_denial_still_blocks_when_access_log_writes_are_disabled(
        self, check_request_access, accesslog_create
    ):
        """Turning the audit INSERT off must not turn ENFORCEMENT off.

        That branch returns early, above the logging block, and nothing covered
        it -- so this is the configuration every test run and every SQLite-backed
        deployment actually uses.
        """
        check_request_access.return_value = (False, "Denied for test")
        request = self.factory.get("/reports/")
        request.META["REMOTE_ADDR"] = "203.0.113.10"

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        accesslog_create.assert_not_called()

    @patch("apps.compliance.middleware.check_request_access")
    def test_access_control_runtime_error_fails_open(self, check_request_access):
        check_request_access.side_effect = RuntimeError("geoip backend unavailable")
        request = self.factory.get("/reports/")

        response = self.middleware.process_request(request)

        self.assertIsNone(response)
