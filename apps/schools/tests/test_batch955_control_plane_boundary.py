"""
PATH §6.12 III.32 / SOT §11.4 batch 955 — school vs platform boundary on public config.

SchoolConfigAPI is the schools-owned AllowAny host-resolved read; mutating HTTP methods
must not be accepted (complements batch 948 rate limit + audit).
"""

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.schools.api_views import SchoolConfigAPI


@override_settings(ALLOWED_HOSTS=["*"])
class Batch955ControlPlaneBoundaryTests(SimpleTestCase):
    """III.32: structural guard — tenant/public config API is GET-only."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_school_config_api_rejects_post_put_patch_delete(self):
        view = SchoolConfigAPI.as_view()
        base_kw = {"HTTP_HOST": "tenant.example.com"}
        for method_name, factory_meth in (
            ("post", self.factory.post),
            ("put", self.factory.put),
            ("patch", self.factory.patch),
            ("delete", self.factory.delete),
        ):
            with self.subTest(method=method_name):
                request = factory_meth("/api/config/", **base_kw)
                request.school = None
                request.user = AnonymousUser()
                response = view(request)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_405_METHOD_NOT_ALLOWED,
                    msg=f"{method_name} must not mutate public config",
                )

    def test_school_config_api_allows_get(self):
        from unittest.mock import patch

        view = SchoolConfigAPI.as_view()
        with patch("apps.api.rate_limit.throttle_ip_request", return_value=(True, 0)):
            with patch(
                "apps.schools.api_views.get_effective_offline_runtime_settings",
                return_value={"enable_offline_mode": False},
            ):
                with patch("apps.schools.api_views.logger"):
                    request = self.factory.get("/api/config/", HTTP_HOST="x.example.com")
                    request.school = None
                    request.user = AnonymousUser()
                    response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
