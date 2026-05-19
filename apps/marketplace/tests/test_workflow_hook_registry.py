"""Manifest workflow_hooks fire on domain events (Linux pillar)."""

from unittest.mock import patch

from django.test import TestCase

from apps.marketplace.models import AppInstallation, MarketplaceApp
from apps.marketplace.workflow_hook_registry import fire_manifest_workflow_hooks
from apps.schools.models import School


class WorkflowHookRegistryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Hook School",
            slug="hook-school",
            subdomain="hook-school",
            is_active=True,
        )
        self.app = MarketplaceApp.objects.create(
            slug="hook-app",
            app_key="hook-app",
            name="Hook App",
            version="1.0.0",
            is_intentionally_free=True,
            manifest={
                "extension_hooks": [
                    {
                        "extension_point": "workflow_hooks",
                        "hook_name": "on_payment",
                        "event_types": ["payment_success"],
                    }
                ]
            },
        )
        AppInstallation.objects.create(
            school=self.school,
            app=self.app,
            status=AppInstallation.Status.ACTIVE,
        )

    @patch("apps.marketplace.workflow_hook_registry.fire")
    def test_manifest_hook_dispatches_trigger(self, mock_fire):
        mock_fire.return_value = [{"ok": True}]
        out = fire_manifest_workflow_hooks(
            self.school, "payment_success", {"amount": "10"}
        )
        self.assertTrue(mock_fire.called)
        self.assertTrue(out)
