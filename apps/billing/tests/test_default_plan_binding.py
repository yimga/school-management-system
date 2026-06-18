"""Default-plan binding: new tenants with no explicit plan get the Free default.

Covers the resolver, the single-default invariant (DWIM switching), new-tenant
auto-binding via ensure_subscription_for_school, and the safety guards
(explicit plan preserved; an existing subscription is never silently rebound).
"""

from decimal import Decimal

from django.test import TestCase

from apps.billing.services import ensure_subscription_for_school
from apps.schools.models import School
from apps.siteconfig.models import Plan


class DefaultPlanResolverTests(TestCase):
    def test_get_default_plan_returns_marked_active_plan(self):
        Plan.objects.create(name="Pro", slug="pro", base_price=Decimal("99.00"), is_active=True)
        free = Plan.objects.create(
            name="Free", slug="free", base_price=Decimal("0.00"), is_active=True, is_default=True
        )
        self.assertEqual(Plan.get_default_plan(), free)

    def test_get_default_plan_none_when_unset(self):
        Plan.objects.create(name="Pro", slug="pro", is_active=True)
        self.assertIsNone(Plan.get_default_plan())

    def test_inactive_default_not_returned(self):
        Plan.objects.create(
            name="Free", slug="free", is_active=False, is_default=True
        )
        self.assertIsNone(Plan.get_default_plan())

    def test_single_default_invariant_dwim(self):
        a = Plan.objects.create(name="Free A", slug="free-a", is_active=True, is_default=True)
        b = Plan.objects.create(name="Free B", slug="free-b", is_active=True)
        # Marking B default must atomically clear A — no IntegrityError.
        b.is_default = True
        b.save()
        a.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertEqual(Plan.objects.filter(is_default=True).count(), 1)
        self.assertEqual(Plan.get_default_plan(), b)


class DefaultPlanBindingTests(TestCase):
    def setUp(self):
        self.free = Plan.objects.create(
            name="Free",
            slug="free",
            base_price=Decimal("0.00"),
            is_active=True,
            is_default=True,
            max_students=50,
        )

    def _school(self, slug, **kw):
        return School.objects.create(
            name=slug, slug=slug, subdomain=slug, is_active=True, **kw
        )

    def test_new_tenant_binds_default_plan(self):
        school = self._school("new-tenant-free")
        self.assertIsNone(school.plan_id)
        _account, subscription, created = ensure_subscription_for_school(school)
        school.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(school.plan, self.free)
        self.assertEqual(subscription.plan, self.free)

    def test_explicit_plan_not_overridden_by_default(self):
        pro = Plan.objects.create(name="Pro", slug="pro", base_price=Decimal("99.00"), is_active=True)
        school = self._school("explicit-plan", plan=pro)
        _account, subscription, _created = ensure_subscription_for_school(school)
        school.refresh_from_db()
        self.assertEqual(school.plan, pro)
        self.assertEqual(subscription.plan, pro)

    def test_no_default_configured_leaves_plan_none(self):
        self.free.is_default = False
        self.free.save()
        school = self._school("no-default")
        ensure_subscription_for_school(school)
        school.refresh_from_db()
        self.assertIsNone(school.plan_id)

    def test_existing_subscription_not_rebound(self):
        # First ensure with NO default configured -> subscription created plan=None.
        self.free.is_default = False
        self.free.save()
        school = self._school("existing-sub")
        ensure_subscription_for_school(school)
        school.refresh_from_db()
        self.assertIsNone(school.plan_id)
        # Now a default exists, but the tenant already has a subscription:
        # ensure must NOT silently rebind an established plan-less tenant.
        self.free.is_default = True
        self.free.save()
        ensure_subscription_for_school(school)
        school.refresh_from_db()
        self.assertIsNone(school.plan_id)
