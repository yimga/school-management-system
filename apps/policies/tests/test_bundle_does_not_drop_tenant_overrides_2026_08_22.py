"""An active policy bundle must not switch off the school's own configuration.

``get_effective_policy`` merges ``TenantBlueprint.active_bundle.policy_snapshot``
when ``POLICY_USE_BUNDLES`` is set -- and that env flag defaults to ON. The bundle
branch then cached and returned immediately, skipping every merge below it: region
defaults (currency, timezone, default_language, rtl), the sector and education
registry merges, the whole ``School.settings`` tenant-override block,
``School.features`` flags, and the TenantAdmissionNumberPolicy backfill.

So adopting a blueprint silently disabled the tenant's own settings -- on a
platform whose headline feature is blueprints.

These pin the precedence that matters: the bundle supplies defaults, the school's
own settings still win on top, and values the bundle never mentions still resolve.
"""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings

from apps.policies.models import PolicyBundle, TenantBlueprint
from apps.policies.resolver import get_effective_policy
from apps.schools.models import School


@override_settings(POLICY_USE_BUNDLES=True, POLICY_CACHE_TTL=0)
class BundleDoesNotDropTenantOverridesTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Bundle High",
            slug=f"bd-{uuid.uuid4().hex[:8]}",
            subdomain=f"bd-{uuid.uuid4().hex[:8]}",
            is_active=True,
            settings={
                "terminology": {"student": "Pupil"},
                "workflows": {"grade_approval_required": True},
            },
        )
        self.bundle = PolicyBundle.objects.create(
            name="Bundle A",
            code=f"bundle-{uuid.uuid4().hex[:8]}",
            is_active=True,
            policy_snapshot={
                "terminology": {"student": "Learner", "teacher": "Facilitator"},
                "grading": {"scale": "0-100"},
            },
        )
        TenantBlueprint.objects.create(school=self.school, active_bundle=self.bundle)

    def test_school_settings_still_override_the_bundle(self) -> None:
        policy = get_effective_policy(self.school)
        self.assertEqual(
            policy["terminology"]["student"],
            "Pupil",
            "School.settings must win over the bundle snapshot",
        )

    def test_bundle_values_the_school_does_not_override_survive(self) -> None:
        policy = get_effective_policy(self.school)
        self.assertEqual(
            policy["terminology"]["teacher"],
            "Facilitator",
            "the bundle is still a defaults layer",
        )

    def test_tenant_workflow_overrides_are_not_dropped(self) -> None:
        policy = get_effective_policy(self.school)
        self.assertTrue(
            policy.get("workflows", {}).get("grade_approval_required"),
            "the School.settings workflows block was skipped entirely before",
        )
