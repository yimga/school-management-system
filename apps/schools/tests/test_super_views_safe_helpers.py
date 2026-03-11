from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase
from django.urls import NoReverseMatch

from apps.schools import super_views


class SuperViewsSafeHelperTests(SimpleTestCase):
    def test_safe_school_admin_change_url_returns_empty_on_missing_route(self):
        with patch("apps.schools.super_views.reverse", side_effect=NoReverseMatch):
            self.assertEqual(super_views._safe_school_admin_change_url(123), "")

    def test_safe_school_timeline_url_returns_empty_on_missing_route(self):
        with patch("apps.schools.super_views.reverse", side_effect=NoReverseMatch):
            self.assertEqual(super_views._safe_school_timeline_url(123), "")

    def test_brand_profile_for_school_returns_none_when_relation_missing(self):
        class MissingBrandProfileSchool:
            @property
            def brand_profile(self):
                raise ObjectDoesNotExist("missing")

        self.assertIsNone(super_views._brand_profile_for_school(MissingBrandProfileSchool()))

    def test_brand_profile_for_school_returns_none_when_attribute_missing(self):
        self.assertIsNone(super_views._brand_profile_for_school(object()))
