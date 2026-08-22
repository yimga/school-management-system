"""Plan-gating ceiling: inert by default, binds only when the flag is ON.

Locks the safety contract of apps/schools/plan_gating.py:
* flag OFF (default) -> is_feature_enabled is the historical pure union (no change);
* flag ON -> a plan-gated code (paid-plan-only) is granted ONLY by an explicit
  plan/addon/School.features/Entitlement grant, never the module/policy union;
* universal codes still resolve via the union even when ON;
* COMPLIMENTARY/MANUAL_OVERRIDE waiver still overrides everything;
* a plan-less school resolves to the default plan, not "unrestricted".
"""
from __future__ import annotations

import os
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School, is_feature_enabled
from apps.schools.plan_gating import (
    clear_plan_gated_cache,
    in_active_trial,
    owner_free_trial_days,
    plan_gated_feature_codes,
    plan_gating_enforced,
)
from apps.siteconfig.models_platform_catalog import Plan


def _enforced():
    return mock.patch.dict(os.environ, {"RMC_PLAN_GATING_ENFORCED": "1"})


class PlanGatingTests(TestCase):
    def setUp(self):
        # Free/default plan grants only the universal "core" module.
        self.free = Plan.objects.create(
            name="Free",
            slug="free-tier",
            included_features=["core"],
            is_default=True,
            is_active=True,
        )
        # Paid plan additionally grants "premium_analytics" -> that code is plan-gated.
        self.paid = Plan.objects.create(
            name="Pro",
            slug="pro-tier",
            included_features=["core", "premium_analytics"],
            is_active=True,
        )
        clear_plan_gated_cache()

    def _school(self, **kwargs):
        defaults = dict(name="S", slug="s1", subdomain="s1", is_active=True)
        defaults.update(kwargs)
        return School.objects.create(**defaults)

    # --- registry derivation -------------------------------------------------

    def test_plan_gated_set_is_paid_only_features(self):
        codes = plan_gated_feature_codes()
        self.assertIn("premium_analytics", codes)
        self.assertNotIn("core", codes)  # in the free plan -> universal

    def test_flag_defaults_off(self):
        self.assertFalse(plan_gating_enforced())

    # --- flag OFF: pure union, no behavior change ----------------------------

    def test_flag_off_ungranted_plan_gated_code_follows_union(self):
        # With the flag OFF the ceiling never runs; a School.features grant still
        # opens the code (historical union behavior) and absence leaves it False.
        school = self._school(plan=self.free)
        self.assertFalse(is_feature_enabled(school, "premium_analytics"))
        school.features = {"premium_analytics": True}
        self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    # --- flag ON: ceiling binds for plan-gated codes -------------------------

    def test_flag_on_denies_ungranted_plan_gated_code(self):
        school = self._school(plan=self.free)
        with _enforced():
            self.assertFalse(is_feature_enabled(school, "premium_analytics"))

    def test_flag_on_plan_include_grants(self):
        school = self._school(plan=self.paid, slug="s-paid", subdomain="s-paid")
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_flag_on_explicit_feature_grant_survives(self):
        # The grandfather snapshot writes School.features; the ceiling must honor it.
        school = self._school(plan=self.free, features={"premium_analytics": True})
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_flag_on_addon_grants(self):
        school = self._school(plan=self.free, addons=["premium_analytics"])
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_flag_on_universal_code_still_uses_union(self):
        # "core" is NOT plan-gated, so even ON it resolves via the union; a
        # School.features grant opens it.
        school = self._school(plan=self.free, features={"core": True})
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "core"))

    def test_flag_on_complimentary_waiver_overrides_ceiling(self):
        school = self._school(plan=self.free, billing_type="COMPLIMENTARY")
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_flag_on_plan_less_resolves_to_default_not_unrestricted(self):
        # No plan bound -> resolve_plan falls to the default (free) plan, which
        # does NOT include premium_analytics -> denied (not "unrestricted").
        school = self._school(plan=None, slug="s-none", subdomain="s-none")
        with _enforced():
            self.assertFalse(is_feature_enabled(school, "premium_analytics"))


class ReverseTrialTests(TestCase):
    def setUp(self):
        self.free = Plan.objects.create(
            name="Free", slug="free-tier", included_features=["core"],
            is_default=True, is_active=True,
        )
        self.paid = Plan.objects.create(
            name="Pro", slug="pro-tier",
            included_features=["core", "premium_analytics"], is_active=True,
        )
        clear_plan_gated_cache()

    def _school(self, **kwargs):
        defaults = dict(name="T", slug="t1", subdomain="t1", is_active=True)
        defaults.update(kwargs)
        return School.objects.create(**defaults)

    def test_owner_free_trial_days_default_is_30(self):
        self.assertEqual(owner_free_trial_days(), 30)

    def test_owner_free_trial_days_env_override(self):
        with mock.patch.dict(os.environ, {"OWNER_FREE_TRIAL_DAYS": "45"}):
            self.assertEqual(owner_free_trial_days(), 45)

    def test_in_active_trial_window(self):
        future = self._school(
            billing_type="FREE_TRIAL",
            trial_end_date=(timezone.now() + timedelta(days=5)).date(),
        )
        self.assertTrue(in_active_trial(future))
        past = self._school(
            slug="t-exp", subdomain="t-exp", billing_type="FREE_TRIAL",
            trial_end_date=(timezone.now() - timedelta(days=1)).date(),
        )
        self.assertFalse(in_active_trial(past))
        regular = self._school(slug="t-reg", subdomain="t-reg", billing_type="REGULAR")
        self.assertFalse(in_active_trial(regular))

    def test_active_trial_grants_full_access_when_enforced(self):
        # Reverse trial: during the window a free-plan trial reaches a plan-gated
        # feature it does not own.
        school = self._school(
            plan=self.free,
            billing_type="FREE_TRIAL",
            trial_end_date=(timezone.now() + timedelta(days=10)).date(),
        )
        with _enforced():
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_expired_trial_downgrades_to_plan_when_enforced(self):
        # The moment the trial date passes, the ceiling binds -> premium denied,
        # WITHOUT any billing-beat flip of billing_type.
        school = self._school(
            slug="t-down", subdomain="t-down",
            plan=self.free,
            billing_type="FREE_TRIAL",  # still FREE_TRIAL, but date has passed
            trial_end_date=(timezone.now() - timedelta(days=1)).date(),
        )
        with _enforced():
            self.assertFalse(is_feature_enabled(school, "premium_analytics"))
            # A universal / plan-included code still resolves.
            self.assertTrue(is_feature_enabled(school, "core"))


class NoActiveDefaultPlanTests(TestCase):
    """The ceiling must fail OPEN when no ACTIVE default plan resolves.

    ``_compute_plan_gated_codes`` derives the gated set as "in some active plan
    but NOT in the default plan". It used to substitute an empty set for the
    default's features when ``get_default_plan()`` returned None, which makes
    *every* feature of *every* active plan plan-gated -- so with the flag ON a
    catalog misconfiguration denies every capability every school reaches
    through the union. These pin the opposite: gate nothing, change nothing.
    """

    def setUp(self):
        self.paid = Plan.objects.create(
            name="Pro",
            slug="pro-tier",
            included_features=["core", "premium_analytics"],
            is_active=True,
        )
        clear_plan_gated_cache()
        self.addCleanup(clear_plan_gated_cache)

    def _school(self, **kwargs):
        defaults = dict(name="S", slug="s2", subdomain="s2", is_active=True)
        defaults.update(kwargs)
        return School.objects.create(**defaults)

    def test_no_default_plan_at_all_gates_nothing(self):
        # Route 1: plans seeded after siteconfig.0200 ran on an empty table, so
        # no row was ever marked default.
        self.assertIsNone(Plan.get_default_plan())
        self.assertEqual(plan_gated_feature_codes(), frozenset())

    def test_flag_on_with_no_default_plan_does_not_lock_out_a_union_grant(self):
        """The regression this class exists for.

        The capability must be reachable ONLY through the union (a module
        manifest / policy toggle) and by no explicit plan, addon, School.features
        or Entitlement grant -- an explicit grant satisfies the ceiling either
        way and so cannot detect the bug. Pre-fix, the absent default plan made
        every feature of every active plan gated, the ceiling demanded an
        explicit grant, found none, and the school silently lost a capability it
        has today.
        """
        school = self._school()
        with mock.patch(
            "apps.siteconfig.tenant_config.get_tenant_modules",
            return_value=["premium_analytics"],
        ):
            # Flag OFF -- the historical union answer, for contrast.
            self.assertTrue(is_feature_enabled(school, "premium_analytics"))
            # Flag ON -- must be unchanged, because a catalog with no default
            # plan gates nothing at all.
            with _enforced():
                self.assertTrue(is_feature_enabled(school, "premium_analytics"))

    def test_inactive_default_plan_is_repaired_not_obeyed(self):
        # Route 2: the plan carrying is_default is deactivated. The check
        # constraint plan_default_must_be_active now refuses that write, so the
        # state cannot arise -- assert the refusal rather than the old fallout.
        from django.db import IntegrityError, transaction

        default = Plan.objects.create(
            name="Free",
            slug="free-tier",
            included_features=["core"],
            is_default=True,
            is_active=True,
        )
        default.is_active = False
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                default.save()

    def test_clean_gives_an_operator_a_sentence_not_an_integrityerror(self):
        from django.core.exceptions import ValidationError

        default = Plan.objects.create(
            name="Free",
            slug="free-tier-2",
            included_features=["core"],
            is_default=True,
            is_active=True,
        )
        default.is_active = False
        with self.assertRaises(ValidationError) as ctx:
            default.full_clean()
        self.assertIn("is_active", ctx.exception.message_dict)
