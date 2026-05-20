"""Core Django runtime integrity: WSGI/ASGI, tenancy mode, test Celery eager."""

from __future__ import annotations

from django.test import SimpleTestCase


class CoreRuntimeIntegrityTests(SimpleTestCase):
    def test_wsgi_application_configured(self):
        from django.conf import settings

        self.assertEqual(settings.WSGI_APPLICATION, "config.wsgi.application")

    def test_celery_eager_when_running_tests(self):
        from django.conf import settings

        if getattr(settings, "RUNNING_TESTS", False):
            self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)

    def test_celery_result_backend_django_db(self):
        from django.conf import settings

        self.assertEqual(settings.CELERY_RESULT_BACKEND, "django-db")

    def test_tenancy_mode_matches_use_django_tenants(self):
        from django.conf import settings

        if settings.TENANCY_MODE == "SCHEMA":
            self.assertTrue(settings.USE_DJANGO_TENANTS)
        elif settings.TENANCY_MODE == "RLS":
            self.assertFalse(settings.USE_DJANGO_TENANTS)

    def test_asgi_when_channels_installed(self):
        from django.conf import settings

        try:
            import channels  # noqa: F401
        except ImportError:
            self.assertIsNone(getattr(settings, "ASGI_APPLICATION", None))
            return
        self.assertEqual(settings.ASGI_APPLICATION, "config.asgi.application")
        self.assertIn("default", getattr(settings, "CHANNEL_LAYERS", {}))
