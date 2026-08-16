"""Edge Onboarding Runbook engine — proves the seven-step bring-up model.

Each test FAILS without ``apps.lifecycle.edge_onboarding`` (import error) and PASSES
once the engine lands. The engine is entirely self-healing, so the suite also proves
that a fresh school yields failing-but-not-exploding validations, that a raising
validate() is caught (never aborts the suite), and that the mandatory dry sync gate
clears only when edge sync is enabled AND the operator is reachable.
"""
from __future__ import annotations

import dataclasses
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.academics.models import AcademicYear
from apps.lifecycle import edge_onboarding
from apps.lifecycle.edge_onboarding import (
    EDGE_ONBOARDING_STEPS,
    generate_runbook,
    heal_step,
    run_sync_gate,
    run_verification_suite,
)
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass

_EXPECTED_KEYS = (
    "provision_shell",
    "migrate_identities",
    "seed_baseline",
    "media_branding",
    "configure_box_env",
    "enable_configure_sync",
    "verify_and_sync_gate",
)


class EdgeOnboardingEngineTests(TestCase):
    SLUG = "gilead-tech"

    def _make_school(self, *, slug=SLUG, active=True):
        with rls_bypass():
            School.objects.filter(slug=slug).delete()
        return School.objects.create(
            id=uuid.uuid4(),
            name="Gilead Technical High School",
            slug=slug,
            subdomain=slug,
            is_active=active,
            is_approved=True,
            country_code="CM",
            settings={},
        )

    # --- generate_runbook -------------------------------------------------- #
    def test_generate_runbook_returns_seven_ordered_filled_steps(self):
        school = self._make_school()
        runbook = generate_runbook(school)
        steps = runbook["steps"]

        self.assertEqual(runbook["total"], 7)
        self.assertEqual(len(steps), 7)
        self.assertEqual(tuple(s["key"] for s in steps), _EXPECTED_KEYS)

        for s in steps:
            # Every runbook line is copy-pasteable and school-specific.
            self.assertTrue(s["command"], f"empty command for {s['key']}")
            self.assertIn(school.slug, s["command"])
            # Placeholders must have been filled — none may survive.
            self.assertNotIn("{slug}", s["command"])
            self.assertNotIn("{school_id}", s["command"])
            self.assertNotIn("{country}", s["command"])
            for required in ("key", "title", "purpose", "command", "workaround"):
                self.assertIn(required, s)
                self.assertTrue(s[required], f"empty {required} for {s['key']}")

        # The {school_id} placeholder is really filled somewhere in the runbook.
        self.assertIn(str(school.id), " ".join(s["command"] for s in steps))

    def test_generate_runbook_is_deterministic(self):
        school = self._make_school()
        self.assertEqual(generate_runbook(school), generate_runbook(school))

    # --- run_verification_suite ------------------------------------------- #
    def test_verification_suite_total_seven_and_never_raises_on_fresh_school(self):
        # A fresh, un-provisioned school: no owner, no academics, no branding.
        school = self._make_school(active=False)
        res = run_verification_suite(school)

        self.assertEqual(res["total"], 7)
        self.assertEqual(len(res["steps"]), 7)
        self.assertIsInstance(res["ok"], bool)
        self.assertFalse(res["ok"])  # a fresh box is not "done"
        self.assertIsInstance(res["passed"], int)

        for s in res["steps"]:
            self.assertIn("key", s)
            self.assertIn("ok", s)
            self.assertIn("detail", s)
            self.assertIsInstance(s["ok"], bool)
            self.assertTrue(s["detail"], f"no detail for {s['key']}")

        failing = [s for s in res["steps"] if not s["ok"]]
        # provision (inactive), identities (no owner), baseline (no academics),
        # branding (no logo), enable-sync (off), sync-gate (off) all fail.
        self.assertGreaterEqual(len(failing), 3)

    def test_verification_suite_catches_a_raising_validate(self):
        school = self._make_school()

        def _boom(_school):
            raise RuntimeError("kaboom")

        patched = list(EDGE_ONBOARDING_STEPS)
        patched[0] = dataclasses.replace(patched[0], validate=_boom)
        with mock.patch.object(edge_onboarding, "EDGE_ONBOARDING_STEPS", tuple(patched)):
            res = run_verification_suite(school)

        self.assertEqual(res["total"], 7)  # suite ran every step despite the raise
        self.assertFalse(res["steps"][0]["ok"])
        self.assertIn("kaboom", res["steps"][0]["detail"])

    # --- run_sync_gate ----------------------------------------------------- #
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_sync_gate_not_cleared_when_disabled(self):
        school = self._make_school()
        res = run_sync_gate(school)  # no patching, no network — flag-gated no-op

        self.assertFalse(res["cleared"])
        self.assertTrue(res["detail"])
        self.assertIn("not enabled", res["detail"].lower())
        self.assertFalse(res["run"]["enabled"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_sync_gate_cleared_when_enabled_and_operator_reachable(self):
        school = self._make_school()
        # Patch the edge transport so the dry probe "succeeds": the delta builds,
        # nothing is posted (dry), and the operator download returns HTTP 200.
        with mock.patch(
            "apps.sync_engine.edge_outbox.build_edge_delta_bundle",
            return_value=(b"bundle", {"row_count": 0, "counts": {}, "high_water_iso": None}),
        ), mock.patch(
            "apps.sync_engine.edge_outbox.post_bundle",
            return_value=(200, {"ok": True}),
        ), mock.patch(
            "apps.sync_engine.edge_outbox.pull_bundle",
            return_value=(200, b"", None),
        ):
            res = run_sync_gate(school)

        self.assertTrue(res["cleared"], res["detail"])
        self.assertTrue(res["run"]["enabled"])
        self.assertTrue(res["run"]["ok"])

    # --- heal_step --------------------------------------------------------- #
    def test_heal_step_without_self_heal_returns_false(self):
        school = self._make_school()
        res = heal_step(school, "verify_and_sync_gate")  # no self-heal defined
        self.assertFalse(res["healed"])
        self.assertIn("no self-heal", res["detail"].lower())

    def test_heal_step_unknown_key_returns_false(self):
        school = self._make_school()
        res = heal_step(school, "does-not-exist")
        self.assertFalse(res["healed"])
        self.assertTrue(res["detail"])

    # --- real checks, not stubs ------------------------------------------- #
    def test_minimally_provisioned_school_passes_the_corresponding_checks(self):
        """active + owner + one AcademicYear (+ an entitlement) makes provision,
        identities, and baseline report ok=True — proving the checks are real."""
        school = self._make_school(active=True)
        User = get_user_model()
        with rls_bypass():
            owner = User.objects.create_user(
                username="gilead_owner",
                email="owner@gilead.school.lan",
                password="x",
            )
            SchoolMembership.objects.create(
                school=school,
                user=owner,
                role="ADMIN",
                is_school_owner=True,
                is_primary=True,
            )
            AcademicYear.objects.create(
                school=school,
                name="2025/2026",
                starts_on="2025-09-01",
                ends_on="2026-07-31",
            )
            from apps.billing.models import Entitlement

            Entitlement.objects.create(school=school, code="reports")

        res = run_verification_suite(school)
        by_key = {s["key"]: s for s in res["steps"]}

        self.assertTrue(by_key["provision_shell"]["ok"], by_key["provision_shell"]["detail"])
        self.assertTrue(by_key["migrate_identities"]["ok"], by_key["migrate_identities"]["detail"])
        self.assertTrue(by_key["seed_baseline"]["ok"], by_key["seed_baseline"]["detail"])
