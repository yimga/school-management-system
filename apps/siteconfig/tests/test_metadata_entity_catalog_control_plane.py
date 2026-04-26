"""Entity catalog overview on manager (siteconfig) — primary operator path vs admin fallbacks."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class EntityCatalogOverviewManagerRouteTests(TestCase):
    databases = {"default"}

    def test_staff_gets_200_with_shell(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_entity_cat",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_entity_cat", password="x" * 8)
        url = reverse("siteconfig:entity_catalog_overview", urlconf="config.manager_urls")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-shell-surface", body)
        self.assertIn("entity-catalog-overview", body)
        self.assertIn("/siteconfig/metadata/entity-catalog/", url)
        self.assertIn("/siteconfig/metadata/operator-hub/", body)

    def test_non_staff_not_200(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_entity_cat_denied", password="y" * 8, is_staff=False
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_entity_cat_denied", password="y" * 8)
        url = reverse("siteconfig:entity_catalog_overview", urlconf="config.manager_urls")
        resp = client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_console_domain_lists_cp_before_admin_labels(self) -> None:
        from apps.siteconfig.views_console_domains import CONSOLE_DOMAINS

        meta = next(d for d in CONSOLE_DOMAINS if d["code"] == "metadata_catalog")
        labels = [label for label, _ in meta["links"]]
        self.assertIn("Metadata & lineage hub", labels)
        self.assertIn("Dynamic fields (EAV operator)", labels)
        self.assertIn("Config mutation audit (evidence)", labels)
        self.assertIn("Entity catalog (overview)", labels)
        hi = labels.index("Metadata & lineage hub")
        dyn = labels.index("Dynamic fields (EAV operator)")
        cm = labels.index("Config mutation audit (evidence)")
        ci = labels.index("Entity catalog (overview)")
        ad = labels.index("Admin: entity rows (CRUD)")
        adf = labels.index("Admin: dynamic field definitions/values (CRUD)")
        self.assertLess(hi, dyn)
        self.assertLess(dyn, cm)
        self.assertLess(cm, ci)
        self.assertLess(ci, ad)
        self.assertLess(ad, adf)

    def test_metadata_operator_hub_manager_route(self) -> None:
        User = get_user_model()
        User.objects.create_user(
            username="cp_meta_hub",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.login(username="cp_meta_hub", password="x" * 8)
        url = reverse("siteconfig:metadata_operator_hub", urlconf="config.manager_urls")
        self.assertIn("/siteconfig/metadata/operator-hub/", url)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-shell-surface", body)
        self.assertIn("metadata-lineage-operator-hub", body)
