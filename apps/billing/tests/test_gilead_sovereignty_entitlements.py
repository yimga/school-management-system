"""gilead-tech sovereignty showcase — grant EVERY platform feature, gilead-only.

The flagship tenant must hold literally everything the platform offers, via
durable MANUAL entitlements (which survive plan reconciliation), and NO other
tenant may be affected.
"""
from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase

from apps.billing.management.commands.ensure_gilead_sovereignty_entitlements import (
    _collect_platform_feature_codes,
)
from apps.billing.models import Entitlement
from apps.schools.models import School


class GileadSovereigntyEntitlementsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_subscription_catalog")
        cls.gilead = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        cls.other = School.objects.create(
            name="Other School", slug="other-school", subdomain="other-school", is_active=True
        )

    def test_collect_feature_codes_is_comprehensive(self):
        codes = _collect_platform_feature_codes()
        self.assertGreater(len(codes), 0)

    def test_grants_every_feature_to_gilead(self):
        call_command("ensure_gilead_sovereignty_entitlements")
        self.gilead.refresh_from_db()
        codes = _collect_platform_feature_codes()

        # Every collected feature is switched ON in School.features.
        feats = self.gilead.features or {}
        for code in codes:
            self.assertTrue(feats.get(code), f"feature {code!r} not enabled on gilead")

        # Every code has a durable MANUAL entitlement (survives reconciliation).
        manual = Entitlement.objects.filter(
            school=self.gilead, source=Entitlement.Source.MANUAL, is_enabled=True
        )
        manual_codes = set(manual.values_list("code", flat=True))
        for code in codes:
            self.assertIn(code, manual_codes, f"no MANUAL entitlement for {code!r}")

        # Plan + complimentary billing.
        self.assertEqual(self.gilead.plan.slug, "sovereign-self-hosted")
        self.assertEqual(self.gilead.billing_type, "COMPLIMENTARY")

    def test_other_tenant_is_untouched(self):
        call_command("ensure_gilead_sovereignty_entitlements")
        self.other.refresh_from_db()
        # No features flipped and no entitlements minted for a non-gilead tenant.
        self.assertFalse(self.other.features)
        self.assertEqual(Entitlement.objects.filter(school=self.other).count(), 0)

    def test_idempotent_second_run(self):
        call_command("ensure_gilead_sovereignty_entitlements")
        call_command("ensure_gilead_sovereignty_entitlements")  # must not raise / duplicate
        codes = _collect_platform_feature_codes()
        manual = Entitlement.objects.filter(
            school=self.gilead, source=Entitlement.Source.MANUAL, is_enabled=True
        )
        # update_or_create keyed on (school, code) → exactly one row per code.
        self.assertEqual(manual.count(), len(codes))
