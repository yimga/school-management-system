"""check_edge_readiness — sovereign/offline edge deployment config validator."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

_LONG_SECRET = "x" * 48


class CheckEdgeReadinessTests(TestCase):
    def _run(self, **kwargs):
        out = StringIO()
        try:
            call_command("check_edge_readiness", stdout=out, stderr=out, **kwargs)
        except CommandError as exc:
            return out.getvalue(), exc
        return out.getvalue(), None

    @override_settings(
        SECRET_KEY=_LONG_SECRET,
        DEBUG=False,
        SINGLE_TENANT=True,
        USE_DJANGO_TENANTS=False,
        ALLOWED_HOSTS=["school.lan", "192.168.1.50"],
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_HSTS_SECONDS=0,
        RMC_DEPLOYMENT_PROFILE="edge",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_healthy_edge_config_reports_ok_lines(self):
        output, err = self._run()
        self.assertIsNone(err)
        self.assertIn("SINGLE_TENANT + shared mode", output)
        self.assertIn("edge", output)
        self.assertIn("plain-HTTP LAN serving", output)  # secure-hardening-off OK line

    @override_settings(
        SECRET_KEY=_LONG_SECRET,
        DEBUG=False,
        SINGLE_TENANT=True,
        USE_DJANGO_TENANTS=True,
        ALLOWED_HOSTS=["school.lan"],
    )
    def test_single_tenant_schema_mode_mismatch_warns(self):
        output, err = self._run(strict=True)  # a WARN must NOT trip --strict
        self.assertIsNone(err)
        self.assertIn("bare-hostname fallback only works in shared/RLS mode", output)

    @override_settings(
        SECRET_KEY="change-me-to-a-long-random-string",  # placeholder → FAIL
        DEBUG=False,
        ALLOWED_HOSTS=["school.lan"],
    )
    def test_placeholder_secret_fails_and_strict_raises(self):
        output, err = self._run(strict=True)
        self.assertIsInstance(err, CommandError)
        self.assertIn("SECRET_KEY", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET,
        DEBUG=False,
        SINGLE_TENANT=False,
        USE_DJANGO_TENANTS=False,
        ALLOWED_HOSTS=["school.lan"],
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_plain_http_secure_cookie_trap_warns(self):
        output, err = self._run()
        self.assertIsNone(err)
        self.assertIn("login will silently fail", output)
