"""Wave 2: Help Center landing + public release notes feed render cleanly."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.feedback.models import ReleaseNote


class HelpCenterAndReleaseNotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="help_user", email="help@example.com", password="pwd"
        )
        ReleaseNote.objects.create(
            title="Help Center wave 2",
            summary="Help Center + public release-notes shipped together.",
            published_at="2026-05-15T00:00:00Z",
            is_public=True,
        )
        ReleaseNote.objects.create(
            title="Internal draft note",
            summary="Should not appear on public feed.",
            is_public=False,
        )

    def setUp(self):
        self.client = Client()

    def test_help_center_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Help Center")
        self.assertContains(response, "Knowledge base")
        self.assertContains(response, "Send feedback")

    def test_release_notes_public_only_shows_published_public_notes(self):
        response = self.client.get(reverse("feedback:release_notes_public"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Help Center wave 2")
        self.assertNotContains(response, "Internal draft note")

    def test_help_center_links_to_release_notes(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("feedback:help_center"))
        self.assertContains(response, reverse("feedback:release_notes_public"))
