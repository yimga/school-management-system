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

    def test_data_bundle_is_a_separate_non_fresh_prep_step(self):
        inputs = BringupInputs(
            slug="gilead-tech",
            bundle_path="/srv/rmc/g.rmcbundle",
            data_bundle_path="/srv/rmc/g-data.rmcbundle",
        )
        actions = plan_prep_actions(inputs)
        keys = [a["key"] for a in actions]
        self.assertIn("provision_shell", keys)
        self.assertIn("seed_operational_data", keys)
        data = next(a for a in actions if a["key"] == "seed_operational_data")
        self.assertEqual(data["cmd"], "import_tenant_bundle")
        self.assertNotIn("--fresh", data["args"])


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

        # The property is that the FAILING step got healed -- not that exactly one
        # heal ran in the whole bring-up. Steps 16-17 (live_sync_proof,
        # go_dark_checklist) are healed explicitly after the gate clears, because
        # they are cloud_preview=False and so never appear in the suite this loop
        # walks. Pinning the total made this test fail the moment the bring-up
        # stopped stopping at step 15.
        healed_keys = [c.args[1] for c in heal.call_args_list]
        self.assertIn("seed_baseline", healed_keys)
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


class GoDarkPhaseTests(TestCase):
    """Live proof + go-dark. The bring-up used to stop before them and call it done.

    It could not have gone further, either: the self-heal loop walks
    run_verification_suite(include_gate=False), which keeps only cloud_preview steps,
    and the box-side checks are cloud_preview=False precisely because their evidence
    lives on the box. So live proof and the checklist are healed explicitly, after
    the gate clears.
    """

    SLUG = "bringup-godark"

    def setUp(self):
        School.objects.filter(slug=self.SLUG).delete()
        School.objects.create(
            name="Bringup GoDark", slug=self.SLUG, subdomain=self.SLUG,
            is_active=True, is_approved=True, country_code="CM", settings={},
        )

    def _run(self, *, gate_cleared=True, healed=True, **kw):
        verification = {"ok": True, "total": 6, "passed": 6, "steps": []}
        gate = {"cleared": gate_cleared, "detail": "gate", "run": {}}
        with mock.patch.object(edge_onboarding, "run_verification_suite", return_value=verification),                 mock.patch.object(edge_onboarding, "run_sync_gate", return_value=gate),                 mock.patch.object(
                    edge_onboarding, "heal_step",
                    return_value={"healed": healed, "detail": "d"},
                ) as heal:
            report = run_edge_bringup(
                inputs=BringupInputs(slug=self.SLUG), runner=_noop_runner, **kw
            )
        return report, heal

    def test_it_heals_the_two_steps_the_preview_can_never_surface(self):
        report, heal = self._run()
        keys = [c.args[1] for c in heal.call_args_list]
        self.assertIn("live_sync_proof", keys)
        self.assertIn("go_dark_checklist", keys)
        self.assertTrue(report["go_dark"]["attempted"])

    def test_the_live_round_trip_is_attempted_before_the_checklist(self):
        # The checklist reads the live run. Evaluating it first measures the previous
        # cycle and calls it today's proof.
        _report, heal = self._run()
        keys = [c.args[1] for c in heal.call_args_list]
        self.assertLess(keys.index("live_sync_proof"), keys.index("go_dark_checklist"))

    def test_a_gate_that_did_not_clear_stops_it_and_says_so(self):
        # Ordering is the reason the gate exists. A live cycle attempted before the
        # gate clears fails for the same reason, and writes a failed LIVE run into
        # the record an operator reads to decide whether this box converges at all.
        report, heal = self._run(gate_cleared=False)
        keys = [c.args[1] for c in heal.call_args_list]
        self.assertNotIn("live_sync_proof", keys)
        self.assertFalse(report["go_dark"]["attempted"])
        self.assertIn("did not clear", report["go_dark"]["detail"])

    def test_not_attempted_reads_differently_from_attempted_and_failed(self):
        # They send somebody to completely different places.
        blocked, _ = self._run(gate_cleared=False)
        failed, _ = self._run(gate_cleared=True, healed=False)
        self.assertFalse(blocked["go_dark"]["attempted"])
        self.assertTrue(failed["go_dark"]["attempted"])
        self.assertFalse(failed["go_dark"]["ok"])

    def test_converged_needs_both_the_gate_and_the_checklist(self):
        cleared, _ = self._run(healed=True)
        self.assertTrue(cleared["converged"])
        not_cleared, _ = self._run(healed=False)
        self.assertFalse(not_cleared["converged"])
        self.assertTrue(not_cleared["offline_ready"], "the weaker claim still holds")

    def test_offline_ready_keeps_its_original_meaning(self):
        # It is pinned by its own tests and by an operator's expectations. Quietly
        # making an existing word stricter turns green runs red for reasons nobody
        # asked about -- so the stronger claim got a new name instead.
        report, _ = self._run(healed=False)
        self.assertTrue(report["offline_ready"])
        self.assertFalse(report["converged"])

    def test_skipping_it_can_never_report_converged(self):
        report, heal = self._run(do_go_dark=False)
        keys = [c.args[1] for c in heal.call_args_list]
        self.assertNotIn("go_dark_checklist", keys)
        self.assertFalse(report["converged"])
        self.assertIsNone(report["go_dark"])
