"""Deliverable D — one-shot edge bring-up orchestrator.

Proves the orchestration + the GO/NO-GO gate without a real box:
  * the prep plan is driven by which file inputs are present;
  * offline_ready is True ONLY when every prep step ran, verification passes, AND the
    sync gate cleared;
  * a not-cleared (or skipped) sync gate is NEVER certified offline-ready — the whole
    point of the mandatory pre-offline gate;
  * a prep-command failure blocks offline-ready;
  * failing verification steps trigger self-heal;
  * a missing school is reported, never crashes.
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.lifecycle import edge_onboarding
from apps.lifecycle.edge_bringup import (
    BringupInputs,
    plan_prep_actions,
    run_edge_bringup,
)
from apps.schools.models import School


def _noop_runner(name, *args):
    return None


class PlanPrepActionsTests(TestCase):
    def test_plan_is_driven_by_present_inputs(self):
        inputs = BringupInputs(
            slug="gilead-tech", country="CM",
            bundle_path="/srv/rmc/g.rmcbundle", brand_path="/srv/rmc/g.rmcbrand",
            mint_credential=True, credential_user="gilead_owner",
        )  # no identity_path
        keys = [a["key"] for a in plan_prep_actions(inputs)]
        self.assertEqual(
            keys, ["provision_shell", "seed_baseline", "media_branding", "enable_configure_sync"]
        )
        # CLI args carry the slug + the file paths verbatim.
        provision = next(a for a in plan_prep_actions(inputs) if a["key"] == "provision_shell")
        self.assertIn("--fresh", provision["args"])
        self.assertIn("/srv/rmc/g.rmcbundle", provision["args"])

    def test_minimal_inputs_plan_is_just_baseline(self):
        keys = [a["key"] for a in plan_prep_actions(BringupInputs(slug="x"))]
        self.assertEqual(keys, ["seed_baseline"])


class RunEdgeBringupTests(TestCase):
    SLUG = "bringup-school"

    def setUp(self):
        self.school = School.objects.create(
            name="Bringup High", slug=self.SLUG, subdomain=self.SLUG,
            is_active=True, is_approved=True, country_code="CM", settings={},
        )

    def _patch(self, *, verify_ok=True, gate_cleared=True):
        verification = {
            "ok": verify_ok, "total": 6, "passed": 6 if verify_ok else 3,
            "steps": [{"key": "seed_baseline", "ok": verify_ok, "detail": "x"}],
        }
        gate = {"cleared": gate_cleared, "detail": "gate", "run": {"enabled": True, "ok": gate_cleared}}
        return (
            mock.patch.object(edge_onboarding, "run_verification_suite", return_value=verification),
            mock.patch.object(edge_onboarding, "run_sync_gate", return_value=gate),
        )

    def test_all_green_is_offline_ready(self):
        vp, gp = self._patch(verify_ok=True, gate_cleared=True)
        with vp, gp:
            report = run_edge_bringup(inputs=BringupInputs(slug=self.SLUG), runner=_noop_runner)
        self.assertTrue(report["offline_ready"])
        self.assertTrue(report["steps_ok"])

    def test_gate_not_cleared_blocks_offline(self):
        vp, gp = self._patch(verify_ok=True, gate_cleared=False)
        with vp, gp:
            report = run_edge_bringup(inputs=BringupInputs(slug=self.SLUG), runner=_noop_runner)
        self.assertFalse(report["offline_ready"])  # gate is mandatory

    def test_skipping_gate_is_never_offline_ready(self):
        vp, gp = self._patch(verify_ok=True, gate_cleared=True)
        with vp, gp:
            report = run_edge_bringup(
                inputs=BringupInputs(slug=self.SLUG), do_sync_gate=False, runner=_noop_runner
            )
        self.assertTrue(report["gate_skipped"])
        self.assertFalse(report["offline_ready"])  # can't certify offline without the gate

    def test_prep_failure_blocks_offline(self):
        def _boom_runner(name, *args):
            if name == "backfill_country_baseline":
                raise RuntimeError("seed failed")

        vp, gp = self._patch(verify_ok=True, gate_cleared=True)
        with vp, gp:
            report = run_edge_bringup(inputs=BringupInputs(slug=self.SLUG), runner=_boom_runner)
        seed = next(e for e in report["prep"] if e["key"] == "seed_baseline")
        self.assertFalse(seed["ok"])
        self.assertIn("seed failed", seed["detail"])
        self.assertFalse(report["offline_ready"])  # a failed prep step is a NO-GO

    def test_self_heal_runs_for_failing_step(self):
        failing = {"ok": False, "total": 6, "passed": 3,
                   "steps": [{"key": "seed_baseline", "ok": False, "detail": "no baseline"}]}
        healed = {"ok": True, "total": 6, "passed": 6,
                  "steps": [{"key": "seed_baseline", "ok": True, "detail": "seeded"}]}
        gate = {"cleared": True, "detail": "gate", "run": {"enabled": True, "ok": True}}

        with mock.patch.object(edge_onboarding, "run_verification_suite", side_effect=[failing, healed]) as verify, \
                mock.patch.object(edge_onboarding, "heal_step", return_value={"healed": True, "detail": "seeded"}) as heal, \
                mock.patch.object(edge_onboarding, "run_sync_gate", return_value=gate):
            report = run_edge_bringup(inputs=BringupInputs(slug=self.SLUG), runner=_noop_runner)

        heal.assert_called_once()
        self.assertEqual(verify.call_count, 2)         # re-verified after heal
        self.assertIn("seed_baseline", report["healed"])
        self.assertTrue(report["offline_ready"])       # heal fixed it → GO

    def test_missing_school_reports_error(self):
        vp, gp = self._patch()
        with vp, gp:
            report = run_edge_bringup(
                inputs=BringupInputs(slug="does-not-exist"), do_prep=False, runner=_noop_runner
            )
        self.assertIn("not found", report["error"])
        self.assertFalse(report["offline_ready"])
