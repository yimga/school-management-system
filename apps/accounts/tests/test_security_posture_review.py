from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.profile_security_evaluation import (
    get_security_posture_review_interval_days,
    is_security_posture_review_due,
    record_security_posture_review,
)

User = get_user_model()


class SecurityPostureReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="posture_user",
            email="posture@example.com",
            password="Str0ngP@ssw0rd!Quarter",
        )
        self.user.password_strength_score = 4
        self.user.password_changed_at = timezone.now()
        self.user.save(
            update_fields=["password_strength_score", "password_changed_at"]
        )

    def test_review_due_when_never_reviewed(self):
        self.assertTrue(is_security_posture_review_due(self.user))

    def test_review_not_due_after_recent_acknowledgement(self):
        record_security_posture_review(self.user)
        self.user.refresh_from_db()
        self.assertFalse(is_security_posture_review_due(self.user))

    def test_review_due_after_interval(self):
        interval = get_security_posture_review_interval_days()
        self.user.last_security_posture_review_at = timezone.now() - timedelta(
            days=interval + 1
        )
        self.user.save(update_fields=["last_security_posture_review_at"])
        self.assertTrue(is_security_posture_review_due(self.user))

    @override_settings(
        MIDDLEWARE=[
            m
            for m in __import__("django.conf", fromlist=["settings"]).settings.MIDDLEWARE
            if "SecurityPostureReviewMiddleware" not in m
        ]
    )
    def test_post_acknowledgement_view_redirects(self):
        self.client.force_login(self.user)
        url = reverse("accounts:security_posture_review")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_security_posture_review_at)
        self.assertFalse(is_security_posture_review_due(self.user))
