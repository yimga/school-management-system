"""Wave 8 (v2.83): user notification-channel preferences UI."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.models_tooling import UserPreference


class NotificationPreferencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="np_user", email="np@example.com", password="pwd"
        )
        cls.other = User.objects.create_user(
            username="np_other", email="other@example.com", password="pwd"
        )

    def setUp(self):
        self.client = Client()

    def test_page_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:notification_preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification preferences")
        self.assertContains(response, "Channels")
        for label in ("Email", "SMS", "App", "WhatsApp"):
            self.assertContains(response, label)

    def test_page_requires_login(self):
        response = self.client.get(reverse("accounts:notification_preferences"))
        self.assertEqual(response.status_code, 302)

    def test_get_creates_userpreference_lazily(self):
        self.client.force_login(self.user)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())
        self.client.get(reverse("accounts:notification_preferences"))
        self.assertTrue(UserPreference.objects.filter(user=self.user).exists())

    def test_post_saves_selected_channels(self):
        self.client.force_login(self.user)
        url = reverse("accounts:notification_preferences")
        response = self.client.post(
            url,
            {
                "notification_channels": ["EMAIL", "APP"],
                "receive_weekly_summary": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(sorted(pref.notification_channels), ["APP", "EMAIL"])
        self.assertTrue(pref.receive_weekly_summary)

    def test_post_clears_weekly_summary_when_unchecked(self):
        UserPreference.objects.create(user=self.user, receive_weekly_summary=True)
        self.client.force_login(self.user)
        self.client.post(
            reverse("accounts:notification_preferences"),
            {"notification_channels": ["EMAIL"]},
        )
        pref = UserPreference.objects.get(user=self.user)
        self.assertFalse(pref.receive_weekly_summary)

    def test_post_filters_unknown_channel_values(self):
        """Defensive: client-tampered POSTs with invalid channels must be dropped."""
        self.client.force_login(self.user)
        self.client.post(
            reverse("accounts:notification_preferences"),
            {"notification_channels": ["EMAIL", "ROGUE_CHANNEL"]},
        )
        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(pref.notification_channels, ["EMAIL"])

    def test_post_does_not_touch_other_users_preferences(self):
        """Tenant + user isolation: my POST cannot mutate another user's prefs."""
        UserPreference.objects.create(
            user=self.other,
            notification_channels=["SMS"],
            receive_weekly_summary=False,
        )
        self.client.force_login(self.user)
        self.client.post(
            reverse("accounts:notification_preferences"),
            {"notification_channels": ["EMAIL", "APP"], "receive_weekly_summary": "1"},
        )
        other_pref = UserPreference.objects.get(user=self.other)
        self.assertEqual(other_pref.notification_channels, ["SMS"])
        self.assertFalse(other_pref.receive_weekly_summary)
