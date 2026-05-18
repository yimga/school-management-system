"""Manager Studio operator toolbar — tenant switcher + mode heroes."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.studio_os.services import get_studio_mode_hero_context, get_studio_operator_toolbar


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
)
class StudioOperatorToolbarTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_toolbar_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        cls.school = School.objects.create(
            name="Toolbar Test School",
            slug="toolbar-test",
            subdomain="toolbar-test",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_toolbar_op", password="x" * 8)

    def test_set_operator_school_sets_session(self):
        url = reverse("studio_os:set_operator_school", urlconf="config.manager_urls")
        studio = reverse("studio_os:shell", urlconf="config.manager_urls")
        resp = self.client.post(
            url,
            {"school_id": str(self.school.pk), "next": studio},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            self.client.session.get("school_id"),
            str(self.school.pk),
        )

    def test_experience_renders_mode_hero_and_toolbar(self):
        url = reverse("studio_os:experience", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-studio-operator-toolbar", body)
        self.assertIn("studio-experience-hero", body)
        self.assertIn("Brand identity", body)

    def test_launch_renders_mode_hero(self):
        url = reverse("studio_os:launch", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("studio-launch-hero", body)
        self.assertIn("Guided onboarding", body)

    def test_live_preview_when_session_school(self):
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        request = self.client.get("/studio/experience/").wsgi_request
        request.urlconf = "config.manager_urls"
        toolbar = get_studio_operator_toolbar(request, current_mode="experience")
        self.assertIsNotNone(toolbar)
        assert toolbar is not None
        self.assertIsNotNone(toolbar.get("live_preview"))
        self.assertEqual(
            toolbar["live_preview"]["school_name"],
            "Toolbar Test School",
        )

    def test_mode_hero_warns_without_tenant(self):
        request = self.client.get("/studio/experience/").wsgi_request
        request.urlconf = "config.manager_urls"
        hero = get_studio_mode_hero_context("experience", request, legacy_urls={})
        self.assertEqual(hero.get("mode_health_status"), "warn")
