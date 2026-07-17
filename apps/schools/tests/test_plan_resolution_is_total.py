"""Every school must resolve to a plan, and provisioning must stamp one.

Owner decision 2026-07-17 (see the pricing model): tenants NEVER pick a plan.
It is stamped at provisioning from the platform default, exactly as every
comparable platform does it -- Salesforce provisions an org from an already
signed subscription, Shopify creates a shop on a real ``trial`` row, Slack on a
real ``Free`` row, and Stripe gives a customer with no subscription NO
entitlements rather than unlimited ones. There is no plan-less tenant anywhere
in the industry, because entitlements have to be computable at all times.

``School.plan`` is nullable and nothing guaranteed it was ever set, so a school
could run forever with ``plan_id = None``. That is only survivable today because
the plan is a GRANTOR rather than a gate (``is_feature_enabled`` unions four
sources and every branch can only say yes), so a missing plan costs the school
nothing -- and therefore the free tier never binds and the upgrade trigger can
never fire.

ORDERING NOTE, load-bearing: stamping a plan was UNSAFE until the default plan
stopped being a fuse. ``free-starter`` carried max_students=50 / max_staff=5 and
``UsageLimitMiddleware`` 403'd every request once a school hit the cap, so
binding the default to a real school would have bricked it at student #51. The
missing plan was what protected live tenants. That fuse is gone (the cap now
refuses only the enrolment, and the default plan is uncapped), so binding is
safe now and was not before.

This change makes resolution TOTAL and binds at provisioning. It deliberately
does NOT make the plan a gate -- that would remove access from live tenants and
is a separate, unapproved decision.
"""

from __future__ import annotations

from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School
from apps.schools.plan_resolution import ensure_school_plan, resolve_plan
from apps.siteconfig.models_platform_catalog import Plan


class ResolvePlanIsTotalTests(TestCase):
    """resolve_plan must answer for every school, not just bound ones."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_subscription_catalog")

    def test_a_plan_less_school_resolves_to_the_platform_default(self):
        school = School.objects.create(
            name="Unbound High", slug="unbound", subdomain="unbound"
        )
        self.assertIsNone(school.plan_id)
        resolved = resolve_plan(school)
        self.assertIsNotNone(
            resolved, "a plan-less school resolved to nothing -- entitlements "
            "must be computable for every school at all times",
        )
        self.assertTrue(resolved.is_default)

    def test_a_bound_school_resolves_to_its_own_plan(self):
        plan = Plan.objects.create(name="Bespoke", slug="bespoke")
        school = School.objects.create(
            name="Bound High", slug="bound", subdomain="bound", plan=plan
        )
        self.assertEqual(resolve_plan(school), plan)

    def test_resolution_never_invents_a_plan_row(self):
        """A read must not write. Defining a plan is a product decision."""
        before = Plan.objects.count()
        School.objects.create(name="RO High", slug="ro", subdomain="ro")
        resolve_plan(School.objects.get(slug="ro"))
        self.assertEqual(Plan.objects.count(), before)

    def test_none_school_resolves_to_none(self):
        self.assertIsNone(resolve_plan(None))


class ResolvePlanWithoutADefaultTests(TestCase):
    """The one honest None: the platform itself is misconfigured."""

    def test_no_default_plan_resolves_to_none_rather_than_raising(self):
        Plan.objects.update(is_default=False)
        school = School.objects.create(
            name="No Default", slug="no-def", subdomain="no-def"
        )
        self.assertIsNone(
            resolve_plan(school),
            "with no is_default plan the resolver must return None, not raise "
            "-- it is read on request paths and must never 500 a tenant",
        )


class EnsureSchoolPlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_subscription_catalog")

    def test_it_binds_the_default_to_a_plan_less_school(self):
        school = School.objects.create(
            name="Bind Me", slug="bind-me", subdomain="bind-me"
        )
        self.assertTrue(ensure_school_plan(school))
        school.refresh_from_db()
        self.assertIsNotNone(school.plan_id)
        self.assertTrue(school.plan.is_default)

    def test_it_never_overrides_an_existing_plan(self):
        """An established tenant's posture is not ours to rewrite."""
        plan = Plan.objects.create(name="Paid", slug="paid-tier")
        school = School.objects.create(
            name="Paying High", slug="paying", subdomain="paying", plan=plan
        )
        self.assertFalse(ensure_school_plan(school))
        school.refresh_from_db()
        self.assertEqual(school.plan_id, plan.pk)

    def test_it_is_idempotent(self):
        school = School.objects.create(
            name="Twice High", slug="twice", subdomain="twice"
        )
        self.assertTrue(ensure_school_plan(school))
        bound = School.objects.get(pk=school.pk).plan_id
        self.assertFalse(ensure_school_plan(School.objects.get(pk=school.pk)))
        self.assertEqual(School.objects.get(pk=school.pk).plan_id, bound)

    def test_the_bound_default_does_not_cap_the_school(self):
        """Binding must not hand a real school a fuse. See the ordering note."""
        school = School.objects.create(
            name="Fuse Check", slug="fuse-check", subdomain="fuse-check"
        )
        ensure_school_plan(school)
        school.refresh_from_db()
        self.assertIsNone(
            school.plan.max_students,
            "provisioning just bound a plan that caps students -- every new "
            "school would be bricked once it enrolled past the cap",
        )
        self.assertIsNone(school.plan.max_staff)


class ProvisioningStampsThePlanTests(TestCase):
    """The wiring: a provisioned school must not come out plan-less."""

    def test_phase_a_activation_binds_a_plan(self):
        from apps.schools import tasks as school_tasks

        school = School.objects.create(
            name="Prov High", slug="prov", subdomain="prov"
        )
        with mock.patch.object(
            school_tasks, "ensure_school_plan"
        ) as ensure, mock.patch.object(
            school_tasks, "_record_school_event"
        ), mock.patch.object(
            school_tasks, "_merge_provisioning_settings"
        ):
            try:
                school_tasks._activate_portal_phase_a(
                    school,
                    school_id=str(school.pk),
                    contact_email="",
                    admin_user=None,
                    wf_run=None,
                    pulse=lambda *a, **k: None,
                )
            except Exception:  # noqa: BLE001 — the optional collaborators this
                # terminus fans out to are not under test; the assertion below
                # is only about whether the plan gets stamped.
                pass
        self.assertTrue(
            ensure.called,
            "Phase A activation completed without binding a plan -- the school "
            "goes live with plan_id=None and the free tier can never bind",
        )
