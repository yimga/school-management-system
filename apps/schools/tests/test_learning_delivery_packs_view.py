"""Super learning delivery & institution types page."""

from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.learning_institution_catalog import (
    INSTITUTION_TYPE_PACKS,
    LEARNING_DELIVERY_MODES,
)


@override_settings(ALLOWED_HOSTS=["*"])
class LearningDeliveryPacksTests(TestCase):
    def test_catalog_matches_sot_wedge_counts(self):
        from apps.platform_runtime.learning_institution_catalog import (
            delivery_wedges,
            institution_wedges,
        )

        self.assertEqual(len(LEARNING_DELIVERY_MODES), 8)
        self.assertEqual(len(INSTITUTION_TYPE_PACKS), 13)
        self.assertEqual(delivery_wedges(), list(range(23, 31)))
        self.assertEqual(institution_wedges(), list(range(31, 44)))

    def test_url_resolves(self):
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            url = reverse("super:learning_delivery_packs")
            self.assertIn("learning-delivery", url)

    def test_template_exists(self):
        p = Path("templates/schools/super_learning_delivery_packs.html")
        self.assertTrue(p.exists())

    def test_get_not_404(self):
        client = Client()
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            r = client.get("/super/learning-delivery-packs/", follow=False)
            self.assertIn(r.status_code, (200, 302))
