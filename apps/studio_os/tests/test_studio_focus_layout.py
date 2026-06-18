"""Wave 1 — manager Studio focus layout (compact sidebar, reduced chrome)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.control_plane_nav import (
    _dedupe_studio_focus_items,
    build_studio_focus_sidebar,
    is_manager_studio_focus_path,
)


class StudioFocusDedupeTests(TestCase):
    """Pure-function guard for the Studio focus-sidebar duplicate-row defect."""

    databases: set = set()

    def test_collapses_same_url_within_one_section(self):
        # The "repeated Workflow gallery in one rail" defect: same url twice in
        # the same section (e.g. registry row + mode-task injection collide).
        items = [
            {"id": "a", "label": "Flow gallery", "url": "/studio/automation/?pane=flow_gallery", "nav_section": "mode_tasks"},
            {"id": "b", "label": "Flow gallery (dup)", "url": "/studio/automation/?pane=flow_gallery", "nav_section": "mode_tasks"},
        ]
        out = _dedupe_studio_focus_items(items)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "a")  # first occurrence wins

    def test_collapses_same_label_within_one_section(self):
        items = [
            {"id": "a", "label": "Workflow center", "url": "/x", "nav_section": "mode_tasks"},
            {"id": "b", "label": "workflow  center", "url": "/y", "nav_section": "mode_tasks"},
        ]
        self.assertEqual(len(_dedupe_studio_focus_items(items)), 1)

    def test_collapses_repeated_id_anywhere(self):
        items = [
            {"id": "dup", "label": "One", "url": "/1", "nav_section": "modes"},
            {"id": "dup", "label": "Two", "url": "/2", "nav_section": "mode_tasks"},
        ]
        self.assertEqual(len(_dedupe_studio_focus_items(items)), 1)

    def test_preserves_same_label_across_different_sections(self):
        # "Overview" is BOTH a work-mode link and the active mode's pane — both
        # must survive (different sections, different urls).
        items = [
            {"id": "mode_overview", "label": "Overview", "url": "/studio/overview/", "nav_section": "modes"},
            {"id": "automation_overview", "label": "Overview", "url": "/studio/automation/?pane=overview", "nav_section": "mode_tasks"},
        ]
        out = _dedupe_studio_focus_items(items)
        self.assertEqual(len(out), 2)


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

    def test_launch_mode_renders_workspace_without_surface_strip(self):
        url = reverse("studio_os:launch", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-workspace="1"', body)
        self.assertIn("data-rmc-studio-workspace-main", body)
        self.assertIn("studio-mode-hero-shell", body)
        self.assertNotIn('data-rmc-operator-surface-strip', body)
        self.assertNotIn('id="studio-rail-label"', body)
