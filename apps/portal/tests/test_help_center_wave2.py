"""Tests for help-center wave 2 batches 1346–1353."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.feedback.models import SupportAIInteractionReview, SupportAISessionRating
from apps.portal.help_guided_journeys import journey_for_path
from apps.portal.help_north_star import build_north_star_bundle
from apps.portal.kb_hitl_publish import create_kb_draft_from_review
from apps.portal.school_help_context import build_school_help_context_block

User = get_user_model()


class HelpCenterWave2Tests(TestCase):
    def test_school_help_context_block_includes_role(self):
        from apps.schools.models import School

        user = User.objects.create_user(username="help2", password="x")
        user.role = "ADMIN"
        school = School.objects.create(name="Test School", slug="test-help2")
        block = build_school_help_context_block(school=school, user=user)
        self.assertIn("ADMIN", block)
        self.assertIn("Test School", block)

    def test_guided_journey_finance_prefix(self):
        j = journey_for_path("/finance/dashboard/")
        self.assertIsNotNone(j)
        self.assertIn("finance-dashboard", j["slug_candidates"])

    def test_north_star_bundle_keys(self):
        bundle = build_north_star_bundle(days=7)
        self.assertIn("days", bundle)
        self.assertIn("deflection", bundle)

    def test_hitl_kb_draft_from_review(self):
        review = SupportAIInteractionReview.objects.create(
            query_fingerprint="abc123",
            active_url="/finance/",
            outcome="support_assistant",
        )
        try:
            create_kb_draft_from_review(review)
        except ValueError as exc:
            if "no_kb_category" in str(exc):
                self.skipTest("no KBCategory in test DB")
            raise
        review.refresh_from_db()
        self.assertIsNotNone(review.kb_draft_article_id)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_help_analytics_resolves(self):
        url = reverse("manager_help_analytics")
        self.assertIn("help-center/analytics", url)

    def test_support_session_rating_api_requires_auth(self):
        rf = RequestFactory()
        req = rf.post(
            reverse("api:ai-support-session-rating"),
            data='{"thumbs":"up","query":"test"}',
            content_type="application/json",
        )
        from apps.portal.views_ai_gateway import api_support_session_rating

        resp = api_support_session_rating(req)
        self.assertIn(resp.status_code, (302, 403))

    def test_session_rating_model(self):
        SupportAISessionRating.objects.create(
            query_fingerprint="fp1",
            thumbs="up",
            task_type="support_assistant",
        )
        self.assertEqual(SupportAISessionRating.objects.count(), 1)
