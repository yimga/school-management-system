"""1066–1067: Dynamic field EAV operator — control plane primary, admin advanced fallback."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class MetadataDynamicFieldsOperatorRouteTests(TestCase):
    databases = {"default"}

    def test_staff_gets_200_with_markers(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_dyn_fields",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_dyn_fields", password="x" * 8)
        url = reverse(
            "siteconfig:metadata_dynamic_fields_operator", urlconf="config.manager_urls"
        )
        self.assertIn("/siteconfig/metadata/dynamic-fields/", url)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-shell-surface", body)
        self.assertIn("metadata-dynamic-fields-operator", body)
        self.assertIn("metadata_dynamic_field_operator", body)

    def test_non_staff_blocked(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_dyn_denied", password="y" * 8, is_staff=False
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_dyn_denied", password="y" * 8)
        url = reverse(
            "siteconfig:metadata_dynamic_fields_operator", urlconf="config.manager_urls"
        )
        resp = client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_superuser_sees_advanced_admin_labels(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_dyn_su",
            password="z" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_dyn_su", password="z" * 8)
        url = reverse(
            "siteconfig:metadata_dynamic_fields_operator", urlconf="config.manager_urls"
        )
        body = client.get(url).content.decode("utf-8", errors="replace")
        self.assertIn("Advanced", body)
        self.assertIn("Admin", body)

    def test_entity_catalog_lists_dynamic_before_admin(self) -> None:
        """Breadcrumb actions: dynamic fields (CP) before Advanced admin buttons."""
        User = get_user_model()
        User.objects.create_user(
            username="cp_ec_order",
            password="w" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_ec_order", password="w" * 8)
        url = reverse("siteconfig:entity_catalog_overview", urlconf="config.manager_urls")
        body = client.get(url).content.decode("utf-8", errors="replace")
        d = body.find("metadata/dynamic-fields/")
        a = body.find("admin/metadata")
        self.assertNotEqual(d, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(d, a)
