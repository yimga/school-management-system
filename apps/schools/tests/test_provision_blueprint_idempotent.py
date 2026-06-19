"""Provisioning idempotency: the onboarding blueprint-pack apply step must be
safe to re-run (requeue / reconcile re-enter _do_provision_tracked).

apply_blueprint_pack() creates a fresh PolicyBundle on every call by design
(that powers version-bump history). The provisioning caller therefore must not
re-apply a pack already applied to the school — otherwise each requeue accrues
a redundant "(applied)" bundle. A *failed* first apply leaves no
TenantBlueprint.applied_pack, so a genuine retry is still allowed.
"""

from __future__ import annotations

from django.test import TestCase

from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
from apps.schools.models import School
from apps.schools.tasks import _maybe_apply_onboarding_blueprint_pack
from apps.siteconfig.models import RegionConfig


class OnboardingBlueprintIdempotencyTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.pack = BlueprintPack.objects.create(
            slug="idempotency-baseline",
            name="Idempotency baseline",
            description="Test pack.",
            policy_snapshot={"feature.x": True},
            is_active=True,
        )
        self.school = School.objects.create(
            name="Idempotency School",
            slug="idempotency-school",
            subdomain="idempotency-school",
            is_active=True,
            default_region=self.region,
            settings={"rmc_public_onboarding": {"pack_slug": self.pack.slug}},
        )

    def test_repeated_provision_applies_pack_once(self):
        # Two provisioning passes (e.g. initial run + a requeue).
        _maybe_apply_onboarding_blueprint_pack(self.school)
        _maybe_apply_onboarding_blueprint_pack(self.school)

        # Exactly one bundle and one tenant-blueprint, despite two passes.
        self.assertEqual(PolicyBundle.objects.filter(school=self.school).count(), 1)
        tb = TenantBlueprint.objects.get(school=self.school)
        self.assertEqual(tb.applied_pack_id, self.pack.pk)

    def test_retry_after_no_prior_apply_still_applies(self):
        # No prior TenantBlueprint → the guard must NOT short-circuit; the pack
        # applies on the first genuine pass.
        self.assertFalse(
            TenantBlueprint.objects.filter(
                school=self.school, applied_pack=self.pack
            ).exists()
        )
        _maybe_apply_onboarding_blueprint_pack(self.school)
        self.assertEqual(PolicyBundle.objects.filter(school=self.school).count(), 1)
