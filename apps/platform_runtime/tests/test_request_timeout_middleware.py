"""RequestTimeoutMiddleware smoke tests."""

from unittest.mock import Mock

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import RequestTimeoutMiddleware


class RequestTimeoutMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(REQUEST_TIMEOUT_SECONDS=0)
    def test_disabled_when_timeout_zero(self):
        def slow(_request):
            return HttpResponse("ok")

        middleware = RequestTimeoutMiddleware(slow)
        response = middleware(self.factory.get("/dashboard/"))
        self.assertEqual(response.status_code, 200)

    @override_settings(REQUEST_TIMEOUT_SECONDS=1)
    def test_skips_static_paths(self):
        middleware = RequestTimeoutMiddleware(Mock())
        response = middleware(self.factory.get("/static/css/app.css"))
        self.assertIsNotNone(response)
