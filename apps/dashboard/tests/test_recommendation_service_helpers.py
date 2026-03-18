from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import NoReverseMatch

from apps.dashboard.recommendation_service import _safe_reverse


class RecommendationServiceHelperTests(SimpleTestCase):
    def test_safe_reverse_returns_fallback_when_route_missing(self):
        with patch(
            "apps.dashboard.recommendation_service.reverse", side_effect=NoReverseMatch
        ):
            self.assertEqual(_safe_reverse("missing:view", "/fallback/"), "/fallback/")
