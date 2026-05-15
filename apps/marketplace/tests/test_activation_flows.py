"""Integration tests for blueprint and app activation flows."""

from django.test import TestCase

from apps.policies.blueprint_services import (
    apply_blueprint_pack,
    preview_blueprint_pack,
)
from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
from apps.schools.models import School


class BlueprintActivationTests(TestCase):
    """Test blueprint pack preview and apply."""

    def test_preview_blueprint_pack_returns_summary(self):
        """Preview returns pack slug, policy_keys, current_bundle_id without writing."""
        school = School.objects.create(
            name="Activation Test School",
            slug="activation-test-school",
            subdomain="activation-test-school",
            is_active=True,
        )
        pack = BlueprintPack.objects.create(
            slug="test-activation-pack",
            name="Test Activation Pack",
            policy_snapshot={
                "admissions": {"numbering_strategy": "annual"},
                "grading": {},
            },
            is_active=True,
        )
        try:
            out = preview_blueprint_pack(school, pack)
            self.assertIn("pack_slug", out)
            self.assertEqual(out["pack_slug"], "test-activation-pack")
            self.assertIn("policy_keys", out)
            self.assertIn("admissions", out["policy_keys"])
            self.assertIsNone(out.get("current_bundle_id"))
        finally:
            pack.delete()

    def test_apply_blueprint_pack_creates_bundle_and_tenant_blueprint(self):
        """Apply creates PolicyBundle and sets TenantBlueprint.active_bundle."""
        school = School.objects.create(
            name="Apply Test School",
            slug="apply-test-school",
            subdomain="apply-test-school",
            is_active=True,
        )
        pack = BlueprintPack.objects.create(
            slug="test-apply-pack",
            name="Test Apply Pack",
            policy_snapshot={
                "admissions": {"numbering_strategy": "full"},
                "grading": {"pass_mark": 50},
            },
            is_active=True,
        )
        try:
            bundle = apply_blueprint_pack(school, pack, applied_by=None)
            self.assertIsInstance(bundle, PolicyBundle)
            self.assertEqual(bundle.school_id, school.id)
            self.assertIn("admissions", bundle.policy_snapshot)
            tb = TenantBlueprint.objects.filter(school=school).first()
            self.assertIsNotNone(tb)
            self.assertEqual(tb.active_bundle_id, bundle.id)
            self.assertEqual(tb.applied_pack_id, pack.id)
        finally:
            TenantBlueprint.objects.filter(school=school).delete()
            PolicyBundle.objects.filter(school=school).delete()
            pack.delete()
