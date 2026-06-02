"""Regression test for the School.clean() parent-hierarchy cycle guard (A1).

The hierarchy cycle detector (`hierarchy_link_would_cycle`) existed but was
never wired into validation, so a cyclic parent_school link (A→B, B→A) could
be saved and then hang every ancestor-chain / hierarchy_path walk. WAVE 4
wired it into `School.clean()`. This test exercises `clean()` DIRECTLY (no
test Client / no GET) so it validates the guard without touching the
request/middleware path — important because that path trips an in-memory
SQLite lock on accounts_user under config.settings_test.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School


class SchoolCycleGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="CG",
            slug=f"cg-{uuid.uuid4().hex[:8]}",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code=f"C{uuid.uuid4().hex[:6].upper()}",
            name="Cgland",
            timezone="UTC",
            default_currency="USD",
        )
        cls.parent = School.objects.create(
            name="Parent District",
            slug="cg-parent",
            subdomain="cg-parent",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.child = School.objects.create(
            name="Child Campus",
            slug="cg-child",
            subdomain="cg-child",
            parent_school=cls.parent,
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )

    def test_direct_cycle_is_rejected(self):
        """parent -> child while child -> parent must raise (would cycle)."""
        self.parent.parent_school = self.child
        with self.assertRaises(ValidationError) as ctx:
            self.parent.clean()
        # message should name the cycle so the operator understands the refusal
        self.assertIn("cycle", str(ctx.exception).lower())

    def test_self_parent_is_rejected(self):
        """A school cannot be its own parent."""
        self.child.parent_school = self.child
        with self.assertRaises(ValidationError):
            self.child.clean()

    def test_valid_hierarchy_link_passes(self):
        """A non-cyclic parent link validates cleanly (no false positive)."""
        sibling = School.objects.create(
            name="Sibling Campus",
            slug="cg-sibling",
            subdomain="cg-sibling",
            is_active=True,
            plan=self.plan,
            default_region=self.region,
        )
        sibling.parent_school = self.parent  # parent has no parent → no cycle
        try:
            sibling.clean()
        except ValidationError as exc:  # pragma: no cover - failure path
            self.fail(f"valid hierarchy link wrongly rejected: {exc}")
