"""Wave 1 — manager Studio focus layout (compact sidebar, reduced chrome)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.control_plane_nav import (
    build_studio_focus_sidebar,
    is_manager_studio_focus_path,
)


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class StudioFocusLayoutTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_focus_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_focus_op", password="x" * 8)

    def test_is_manager_studio_focus_path(self):
        self.assertTrue(is_manager_studio_focus_path("/studio/control/"))
        self.assertTrue(is_manager_studio_focus_path("/studio"))
        self.assertFalse(is_manager_studio_focus_path("/super/dashboard/"))

    def test_build_studio_focus_sidebar_has_modes(self):
        request = self.client.get("/studio/").wsgi_request
        request.urlconf = "config.manager_urls"
        items = build_studio_focus_sidebar(request)
        labels = {it["label"] for it in items}
        self.assertIn("Control", labels)
        self.assertIn("Experience", labels)
        ids = [it["id"] for it in items]
        self.assertEqual(len(ids), len(set(ids)))
        item_labels = [it["label"] for it in items]
        self.assertEqual(len(item_labels), len(set(item_labels)))

    def test_build_studio_focus_sidebar_control_includes_governance(self):
        request = self.client.get("/studio/control/").wsgi_request
        request.urlconf = "config.manager_urls"
        items = build_studio_focus_sidebar(request)
        labels = [it["label"] for it in items]
        self.assertIn("Feature control", labels)
        self.assertIn("Audit log", labels)
        self.assertNotIn("Command center", labels)

    def test_build_studio_focus_sidebar_launch_includes_panes(self):
        request = self.client.get("/studio/launch/?pane=onboarding").wsgi_request
        request.urlconf = "config.manager_urls"
        items = build_studio_focus_sidebar(request)
        labels = [it["label"] for it in items]
        self.assertIn("Guided onboarding", labels)
        active = [it for it in items if it.get("active")]
        self.assertTrue(any(it.get("label") == "Guided onboarding" for it in active))

    def test_automation_mode_renders_hero_and_single_rail(self):
        url = reverse("studio_os:automation", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("studio-mode-hero-shell", body)
        self.assertIn("Workflow center", body)
        self.assertNotIn('id="studio-rail-label"', body)

    def test_control_mode_renders_focus_markers(self):
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:400])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-focus="1"', body)
        self.assertIn("data-rmc-studio-focus-sidebar", body)
        self.assertIn("studio-focus-layout.css", body)
        self.assertNotIn("Curriculum &amp; region", body)
        self.assertNotIn("Curriculum & region", body)
        self.assertNotIn('id="studio-rail-label"', body)
        self.assertNotIn('id="control-rail-list"', body)
        self.assertIn("Governance", body)

    def test_experience_mode_renders_focus_markers(self):
        url = reverse("studio_os:experience", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-focus="1"', body)
        self.assertIn("data-rmc-studio-focus-sidebar", body)
