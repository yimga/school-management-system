"""1071: Config mutation audit evidence — read-only CP, admin advanced fallback."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class ConfigMutationAuditEvidenceRouteTests(TestCase):
    databases = {"default"}

    def test_staff_gets_200_with_markers(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_cfg_mut",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_cfg_mut", password="x" * 8)
        url = reverse(
            "siteconfig:config_mutation_audit_evidence",
            urlconf="config.manager_urls",
        )
        self.assertIn("/siteconfig/metadata/config-mutation-audit/", url)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-shell-surface", body)
        self.assertIn("config-mutation-audit-evidence", body)

    def test_non_staff_blocked(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_cfg_mut_denied", password="y" * 8, is_staff=False
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_cfg_mut_denied", password="y" * 8)
        url = reverse(
            "siteconfig:config_mutation_audit_evidence",
            urlconf="config.manager_urls",
        )
        resp = client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_superuser_sees_advanced_admin(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_cfg_mut_su",
            password="z" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_cfg_mut_su", password="z" * 8)
        url = reverse(
            "siteconfig:config_mutation_audit_evidence",
            urlconf="config.manager_urls",
        )
        body = client.get(url).content.decode("utf-8", errors="replace")
        self.assertIn("Advanced", body)
        self.assertIn("Admin", body)
