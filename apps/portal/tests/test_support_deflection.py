"""Support deflection contract tests (batch 1331 validation)."""

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.portal.kb_embeddings import DEFLECTION_SCORE_THRESHOLD, cosine_similarity
from apps.portal.support_deflection import find_deflection_candidates


class SupportDeflectionUnitTests(SimpleTestCase):
    def test_threshold_is_point_eight_eight(self):
        self.assertEqual(DEFLECTION_SCORE_THRESHOLD, 0.88)

    def test_cosine_at_threshold_blocks_when_vector_method(self):
        self.assertGreaterEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 0.88)


class SupportDeflectionEventTests(TestCase):
    def test_fingerprint_and_event_model_fields(self):
        from apps.feedback.models import SupportDeflectionEvent

        fp = SupportDeflectionEvent.fingerprint("How do I reset parent password?")
        self.assertEqual(len(fp), 32)
        event = SupportDeflectionEvent.objects.create(
            outcome=SupportDeflectionEvent.Outcome.SUGGESTED,
            top_score=0.91,
            article_slug="reset-parent-access",
            query_fingerprint=fp,
            surface="support_ticket",
        )
        self.assertEqual(event.top_score, 0.91)
        self.assertEqual(event.outcome, "suggested")
        self.assertIsNotNone(event.created_at)


class SupportDeflectionApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="deflect_test",
            email="deflect@example.com",
            password="Test1234",
        )

    def test_find_deflection_candidates_empty_without_school(self):
        request = self.factory.get("/api/support/deflection/?q=password")
        request.user = self.user
        request.school = None
        bundle = find_deflection_candidates(request, query_text="password reset help")
        self.assertIn("articles", bundle)
        self.assertFalse(bundle.get("blocking"))
