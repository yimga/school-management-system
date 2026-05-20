"""HITL AI review queue — batch 1340 gap-close tests."""

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings

from apps.feedback.models import SupportAIInteractionReview
from config.manager_ai_review_queue import manager_ai_review_queue

User = get_user_model()


@override_settings(ROOT_URLCONF="config.manager_urls")
class ManagerAiReviewQueueTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="hitl_staff",
            password="test-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.review = SupportAIInteractionReview.objects.create(
            query_fingerprint="abc123",
            status=SupportAIInteractionReview.Status.PENDING,
            is_operator=True,
        )
        self.factory = RequestFactory()

    def _attach_session(self, request):
        request.session = {}
        request._messages = FallbackStorage(request)

    def test_resolve_sets_note_and_resolved_at(self):
        request = self.factory.post(
            "/help-center/ai-review/",
            data={
                "review_id": str(self.review.pk),
                "action": "resolve",
                "note": "Linked runbook updated",
            },
        )
        request.user = self.staff
        self._attach_session(request)
        response = manager_ai_review_queue(request)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, SupportAIInteractionReview.Status.RESOLVED)
        self.assertEqual(self.review.note, "Linked runbook updated")
        self.assertIsNotNone(self.review.resolved_at)
