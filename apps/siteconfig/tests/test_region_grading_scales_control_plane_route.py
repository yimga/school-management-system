"""Wave A: region grading scales matrix reachable on manager (control-plane), not only /admin."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class RegionGradingScalesManagerRouteTests(TestCase):
    databases = {"default"}

    def test_staff_gets_200_on_siteconfig_route(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_grading_matrix",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_grading_matrix", password="x" * 8)
        url = reverse("siteconfig:region_grading_scales", urlconf="config.manager_urls")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:400])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("scale", body.lower())
