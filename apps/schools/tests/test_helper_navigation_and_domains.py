from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch

from apps.schools.control_plane_nav import _safe_reverse
from apps.schools.views_domains import api_domains_list_or_create


class SchoolHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_safe_reverse_returns_none_on_missing_route(self):
        with patch("apps.schools.control_plane_nav.reverse", side_effect=NoReverseMatch):
            self.assertIsNone(_safe_reverse("missing:view"))

    def test_api_domains_create_returns_error_for_invalid_json_without_touching_db(self):
        request = self.factory.post(
            "/api/tenant/domains/",
            data="{invalid",
            content_type="application/json",
        )
        request.user = SimpleNamespace(is_authenticated=True)
        request.school = object()

        with patch("apps.schools.views_domains._require_school_admin", return_value=True):
            response = api_domains_list_or_create(request)

        self.assertEqual(response.status_code, 400)
