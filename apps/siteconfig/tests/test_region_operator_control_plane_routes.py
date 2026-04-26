"""Region validation, comparison, and grading matrix: manager control-plane routes (not /admin)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class RegionOperatorSurfacesManagerRouteTests(TestCase):
    """Staff/superuser reach region operator surfaces on manager host with control-plane shell markers."""

    databases = {"default"}

    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cp_region_ops",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def _get(self, view_name: str) -> tuple[object, str]:
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_region_ops", password="x" * 8)
        url = reverse(view_name, urlconf="config.manager_urls")
        resp = client.get(url)
        body = (
            resp.content.decode("utf-8", errors="replace")
            if resp.status_code == 200
            else ""
        )
        return resp, body

    def test_region_grading_scales_200_with_shell(self) -> None:
        resp, body = self._get("siteconfig:region_grading_scales")
        self.assertEqual(resp.status_code, 200, msg=body[:500])
        self.assertIn("data-shell-surface", body)
        self.assertIn("data-rmc-shell-root", body)
        self.assertIn("scale", body.lower())

    def test_region_validation_200_with_shell(self) -> None:
        resp, body = self._get("siteconfig:region_validation")
        self.assertEqual(resp.status_code, 200, msg=body[:500])
        self.assertIn("data-shell-surface", body)
        self.assertIn("data-page-archetype", body)
        self.assertIn("data-rmc-shell-root", body)
        self.assertIn("region-validation-dashboard", body)

    def test_region_comparison_200_with_shell(self) -> None:
        resp, body = self._get("siteconfig:region_comparison")
        self.assertEqual(resp.status_code, 200, msg=body[:500])
        self.assertIn("data-shell-surface", body)
        self.assertIn("data-rmc-shell-root", body)
        self.assertIn("region-comparison-matrix", body)

    def test_non_staff_403(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_region_denied", password="y" * 8, is_staff=False
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_region_denied", password="y" * 8)
        for name in (
            "siteconfig:region_grading_scales",
            "siteconfig:region_validation",
            "siteconfig:region_comparison",
        ):
            url = reverse(name, urlconf="config.manager_urls")
            resp = client.get(url)
            self.assertIn(
                resp.status_code,
                (302, 403),
                msg=f"{name} -> {resp.status_code}",
            )
