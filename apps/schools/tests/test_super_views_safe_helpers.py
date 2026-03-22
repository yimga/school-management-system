from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase
from django.urls import NoReverseMatch

from apps.schools.super_views_dashboard_helpers import (
    brand_profile_for_school,
    safe_registry_url,
)
from apps.schools.super_views_helpers import (
    _safe_school_admin_change_url,
    _safe_school_timeline_url,
)


class SuperViewsSafeHelperTests(SimpleTestCase):
    def test_safe_school_admin_change_url_returns_empty_on_missing_route(self):
        with patch("apps.schools.super_views_helpers.reverse", side_effect=NoReverseMatch):
            self.assertEqual(_safe_school_admin_change_url(123), "")

    def test_safe_school_timeline_url_returns_empty_on_missing_route(self):
        with patch("apps.schools.super_views_helpers.reverse", side_effect=NoReverseMatch):
            self.assertEqual(_safe_school_timeline_url(123), "")

    def test_safe_registry_url_returns_empty_on_missing_route(self):
        with patch(
            "apps.schools.super_views_dashboard_helpers.reverse",
            side_effect=NoReverseMatch,
        ):
            self.assertEqual(safe_registry_url(), "")

    def test_brand_profile_for_school_returns_none_when_relation_missing(self):
        class MissingBrandProfileSchool:
            @property
            def brand_profile(self):
                raise ObjectDoesNotExist("missing")

        self.assertIsNone(
            brand_profile_for_school(MissingBrandProfileSchool())
        )

    def test_brand_profile_for_school_returns_none_when_attribute_missing(self):
        self.assertIsNone(brand_profile_for_school(object()))
