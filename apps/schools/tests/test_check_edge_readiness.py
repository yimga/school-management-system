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

    # --- Tier 2 external-dependency offline-correctness checks ---------------

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        RMC_DEPLOYMENT_PROFILE="edge",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_offline_email_queue_on_reports_ok(self):
        output, err = self._run()
        self.assertIsNone(err)
        self.assertIn("offline email queue ON", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        RMC_DEPLOYMENT_PROFILE="online", RMC_EMAIL_OFFLINE_QUEUE=False,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_console_backend_without_offline_queue_warns(self):
        output, err = self._run()
        self.assertIn("silently DROPPED", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        RMC_AUTO_ENQUEUE_OUTBOUND="0",
    )
    def test_sms_auto_enqueue_off_warns(self):
        output, err = self._run()
        self.assertIn("failed SMS/WhatsApp send is LOST", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        CELERY_BROKER_URL="",
    )
    def test_no_broker_warns_to_cron_drain(self):
        output, err = self._run()
        self.assertIn("drain_edge_outbox", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND="aws-kms",
    )
    def test_cloud_signing_backend_warns(self):
        output, err = self._run(strict=True)  # WARN must not trip --strict
        self.assertIsNone(err)
        self.assertIn("network-bound", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        RMC_GATEWAY_COLLECTION_ENABLED=True,
    )
    def test_payment_collection_enabled_warns(self):
        output, err = self._run()
        self.assertIn("FAILS CLOSED offline", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"], CELERY_BROKER_URL="",
    )
    def test_broker_less_recommends_run_periodic_jobs(self):
        output, err = self._run()
        self.assertIn("run_periodic_jobs", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_local_media_backend_warns_about_durability(self):
        output, err = self._run()
        self.assertIn("Media is on the LOCAL filesystem", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        STORAGES={
            "default": {"BACKEND": "storages.backends.s3.S3Storage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )
    def test_object_storage_media_backend_ok(self):
        output, err = self._run()
        self.assertIn("object-storage backend", output)

    @override_settings(
        SECRET_KEY=_LONG_SECRET, DEBUG=False, ALLOWED_HOSTS=["school.lan"],
        RMC_DEPLOYMENT_PROFILE="edge", OLLAMA_ENDPOINT="",
    )
    def test_edge_profile_without_ollama_endpoint_warns(self):
        output, err = self._run()
        self.assertIn("OLLAMA_ENDPOINT is unset", output)
