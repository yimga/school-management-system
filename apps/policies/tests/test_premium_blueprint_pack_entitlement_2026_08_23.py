"""A premium commercial blueprint pack must not apply without an entitlement.

``apply_blueprint_pack`` gated on ``pack.is_active`` and nothing else.
``BlueprintPack.is_premium_commercial`` ("apply/upgrade may require commercial
entitlement") and ``list_price`` existed only in the model, the migration and two
admin list columns -- no code anywhere consulted either. Meanwhile the
UNAUTHENTICATED signup wizard builds its pack picker from
``BlueprintPack.objects.filter(is_active=True)`` with no premium filter, stashes the
posted ``pack_slug`` in the session, and provisioning re-looks it up with the same
filter and applies it. So a self-signup user could POST the slug of a
4,999.00-list-price pack -- shown in the picker, or hand-crafted -- and the tenant
came up on the paid pack with no entitlement, no billing record and no audit
distinction from a free pack.

The gate is deliberately an EXPLICIT billing ``Entitlement`` row, not
``is_feature_enabled``/``entitlements.can``: those resolve a union of plan features,
add-ons, module manifests and an operator floor, and a commercial gate a module
manifest can open is not a commercial gate.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Entitlement
from apps.policies.blueprint_services import (
    EntitlementRequired,
    apply_blueprint_pack,
    preview_blueprint_pack,
    premium_entitlement_codes,
)
from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
from apps.schools.models import School


def _make_school() -> School:
    tag = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"Pack High {tag}",
        slug=f"pk-{tag}",
        subdomain=f"pk-{tag}",
        is_active=True,
    )


def _make_pack(*, premium: bool) -> BlueprintPack:
    tag = uuid.uuid4().hex[:8]
    return BlueprintPack.objects.create(
        slug=f"pack-{tag}",
        name=f"Pack {tag}",
        is_active=True,
        is_premium_commercial=premium,
        list_price=Decimal("4999.00") if premium else Decimal("0.00"),
        policy_snapshot={"terminology": {"student": "Candidate"}},
    )


class PremiumPackRequiresEntitlementTests(TestCase):
    def setUp(self) -> None:
        self.school = _make_school()

    def _grant(self, code: str, **kwargs) -> Entitlement:
        return Entitlement.objects.create(
            school=self.school,
            code=code,
            kind=Entitlement.Kind.FEATURE,
            source=Entitlement.Source.MANUAL,
            **kwargs,
        )

    def test_free_pack_still_applies(self) -> None:
        """Non-vacuity: the apply path itself works -- the gate is what refuses."""
        pack = _make_pack(premium=False)
        bundle = apply_blueprint_pack(self.school, pack)
        self.assertIsInstance(bundle, PolicyBundle)
        self.assertEqual(bundle.policy_snapshot, pack.policy_snapshot)
        self.assertTrue(
            TenantBlueprint.objects.filter(
                school=self.school, applied_pack=pack
            ).exists()
        )

    def test_premium_pack_without_entitlement_is_refused(self) -> None:
        pack = _make_pack(premium=True)
        with self.assertRaises(EntitlementRequired) as ctx:
            apply_blueprint_pack(self.school, pack)
        self.assertIn(pack.slug, str(ctx.exception))
        # Nothing was half-written: no bundle, no TenantBlueprint.
        self.assertFalse(PolicyBundle.objects.filter(school=self.school).exists())
        self.assertFalse(TenantBlueprint.objects.filter(school=self.school).exists())

    def test_premium_pack_applies_with_a_pack_scoped_entitlement(self) -> None:
        pack = _make_pack(premium=True)
        self._grant(f"blueprint_pack:{pack.slug}")
        bundle = apply_blueprint_pack(self.school, pack)
        self.assertEqual(bundle.applied_pack_version, pack.version)

    def test_premium_pack_applies_with_the_blanket_entitlement(self) -> None:
        pack = _make_pack(premium=True)
        self._grant("premium_blueprints")
        self.assertIsInstance(apply_blueprint_pack(self.school, pack), PolicyBundle)

    def test_entitlement_for_a_different_pack_does_not_grant(self) -> None:
        pack = _make_pack(premium=True)
        other = _make_pack(premium=True)
        self._grant(f"blueprint_pack:{other.slug}")
        # Non-vacuity: the grant IS a working grant -- for the pack it names.
        self.assertIsInstance(apply_blueprint_pack(self.school, other), PolicyBundle)
        with self.assertRaises(EntitlementRequired):
            apply_blueprint_pack(self.school, pack)

    def test_disabled_entitlement_does_not_grant(self) -> None:
        pack = _make_pack(premium=True)
        self._grant(f"blueprint_pack:{pack.slug}", is_enabled=False)
        with self.assertRaises(EntitlementRequired):
            apply_blueprint_pack(self.school, pack)

    def test_expired_entitlement_does_not_grant(self) -> None:
        pack = _make_pack(premium=True)
        now = timezone.now()
        self._grant(
            f"blueprint_pack:{pack.slug}",
            effective_from=now - timedelta(days=60),
            effective_until=now - timedelta(days=1),
        )
        with self.assertRaises(EntitlementRequired):
            apply_blueprint_pack(self.school, pack)

    def test_not_yet_effective_entitlement_does_not_grant(self) -> None:
        pack = _make_pack(premium=True)
        self._grant(
            f"blueprint_pack:{pack.slug}",
            effective_from=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(EntitlementRequired):
            apply_blueprint_pack(self.school, pack)

    def test_another_schools_entitlement_does_not_grant(self) -> None:
        pack = _make_pack(premium=True)
        other_school = _make_school()
        Entitlement.objects.create(
            school=other_school,
            code=f"blueprint_pack:{pack.slug}",
            kind=Entitlement.Kind.FEATURE,
        )
        with self.assertRaises(EntitlementRequired):
            apply_blueprint_pack(self.school, pack)
        # Non-vacuity: that same row DOES grant, for the school it belongs to.
        self.assertIsInstance(
            apply_blueprint_pack(other_school, pack), PolicyBundle
        )

    def test_inactive_pack_check_still_comes_first(self) -> None:
        pack = _make_pack(premium=True)
        pack.is_active = False
        pack.save(update_fields=["is_active"])
        with self.assertRaises(ValueError) as ctx:
            apply_blueprint_pack(self.school, pack)
        self.assertNotIsInstance(ctx.exception, EntitlementRequired)

    def test_entitlement_codes_are_pack_scoped_then_blanket(self) -> None:
        pack = _make_pack(premium=True)
        self.assertEqual(
            premium_entitlement_codes(pack),
            [f"blueprint_pack:{pack.slug}", "premium_blueprints"],
        )


class PremiumPackPreviewReportsEntitlementTests(TestCase):
    def setUp(self) -> None:
        self.school = _make_school()

    def test_preview_of_a_free_pack_requires_nothing(self) -> None:
        pack = _make_pack(premium=False)
        preview = preview_blueprint_pack(self.school, pack)
        # Non-vacuity: the preview really ran and produced its normal payload.
        self.assertEqual(preview["pack_slug"], pack.slug)
        self.assertEqual(preview["policy_keys"], ["terminology"])
        self.assertFalse(preview["requires_entitlement"])
        self.assertTrue(preview["entitlement_satisfied"])

    def test_preview_of_a_premium_pack_reports_the_missing_entitlement(self) -> None:
        pack = _make_pack(premium=True)
        preview = preview_blueprint_pack(self.school, pack)
        self.assertEqual(preview["pack_slug"], pack.slug)
        self.assertTrue(preview["requires_entitlement"])
        self.assertFalse(preview["entitlement_satisfied"])
        self.assertEqual(
            preview["entitlement_codes"],
            [f"blueprint_pack:{pack.slug}", "premium_blueprints"],
        )

    def test_preview_of_an_entitled_premium_pack_reports_satisfied(self) -> None:
        pack = _make_pack(premium=True)
        Entitlement.objects.create(
            school=self.school,
            code="premium_blueprints",
            kind=Entitlement.Kind.FEATURE,
        )
        preview = preview_blueprint_pack(self.school, pack)
        self.assertTrue(preview["requires_entitlement"])
        self.assertTrue(preview["entitlement_satisfied"])
