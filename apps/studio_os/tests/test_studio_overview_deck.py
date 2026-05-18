"""Studio OS command deck — /studio/ home overview."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.studio_os.services import get_studio_overview_deck
from apps.studio_os.views import STUDIO_MODES


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class StudioOverviewDeckTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_deck_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_deck_op", password="x" * 8)

    def test_get_studio_overview_deck_mode_cards(self):
        request = self.client.get("/studio/").wsgi_request
        request.urlconf = "config.manager_urls"
        deck = get_studio_overview_deck(request, modes=STUDIO_MODES)
        self.assertEqual(len(deck["mode_cards"]), 5)
        self.assertTrue(deck["mode_cards"][0]["url"])
        self.assertEqual(deck["mode_cards"][0]["shortcut_digit"], "1")

    def test_manager_home_renders_command_deck(self):
        url = reverse("studio_os:shell", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-studio-command-deck", body)
        self.assertIn("studio-command-deck.css", body)
        self.assertIn("studio_os__overview_deck.js", body)
        self.assertIn("Pick a tenant for live preview", body)
