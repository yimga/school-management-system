"""Linux pillar: install blocked when extension manifest is invalid."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.marketplace.lifecycle import install_app
from apps.marketplace.models import MarketplaceApp, MarketplaceListing
from apps.marketplace.services import ensure_marketplace_listing
from apps.schools.models import School


class InstallManifestGateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(
            name="Manifest Gate School",
            slug="manifest-gate",
            subdomain="manifest-gate",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="manifest_gate_admin",
            password="Test1234",
            role="ADMIN",
        )
        self.app = MarketplaceApp.objects.create(
            slug="bad-ext-app",
            app_key="bad-ext-app",
            name="Bad Ext",
            version="1.0.0",
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=True,
            manifest={
                "extension_hooks": [
                    {"extension_point": "workflow_hooks", "hook_name": "x"}
                ]
            },
        )
        ensure_marketplace_listing(self.app)

    def test_install_rejects_incomplete_extension_manifest(self):
        with self.assertRaises(ValueError) as ctx:
            install_app(school=self.school, app=self.app, actor=self.actor)
        self.assertIn("extension manifest", str(ctx.exception).lower())

    def test_install_accepts_valid_extension_manifest(self):
        self.app.manifest = {
            "extension_hooks": [
                {
                    "extension_point": "workflow_hooks",
                    "hook_name": "post_enrollment",
                    "event_types": ["student.enrolled"],
                }
            ]
        }
        self.app.save(update_fields=["manifest"])
        inst = install_app(school=self.school, app=self.app, actor=self.actor)
        self.assertEqual(inst.app_id, self.app.pk)
