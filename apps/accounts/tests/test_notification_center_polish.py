"""Wave 3 (v2.70): notification center polish — mark-all-read SSR action."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.finance.models import Notification


class MarkAllNotificationsReadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="inbox_user", email="inbox@example.com", password="pwd"
        )
        cls.other = User.objects.create_user(
            username="other_user", email="other@example.com", password="pwd"
        )
        for i in range(3):
            Notification.objects.create(
                recipient=cls.user,
                title=f"Unread {i}",
                message="payload",
                is_read=False,
            )
        Notification.objects.create(
            recipient=cls.user,
            title="Already read",
            message="payload",
            is_read=True,
        )
        Notification.objects.create(
            recipient=cls.other,
            title="Other user's note",
            message="payload",
            is_read=False,
        )

    def setUp(self):
        self.client = Client()

    def test_mark_all_read_marks_only_callers_unread(self):
        self.client.force_login(self.user)
        url = reverse("accounts:mark_all_notifications_read")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, is_read=False).count(),
            0,
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.other, is_read=False).count(),
            1,
            "Other user's unread must remain untouched (tenant + user isolation).",
        )

    def test_mark_all_read_requires_post(self):
        self.client.force_login(self.user)
        url = reverse("accounts:mark_all_notifications_read")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_mark_all_read_requires_authentication(self):
        url = reverse("accounts:mark_all_notifications_read")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"].lower() + "/accounts/login/")

    def test_notifications_page_renders_mark_all_button_when_unread(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:user_notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mark all read")
        self.assertContains(
            response, reverse("accounts:mark_all_notifications_read")
        )

    def test_notifications_page_hides_mark_all_button_when_clean(self):
        Notification.objects.filter(recipient=self.user).update(is_read=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:user_notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Mark all read")
