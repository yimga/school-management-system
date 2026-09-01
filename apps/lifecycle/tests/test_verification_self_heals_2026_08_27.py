"""Three steps that printed a command and waited, instead of running their own check.

`verify_and_sync_gate`, `live_sync_proof` and `go_dark_checklist` each asked for
evidence the box can generate about itself -- a dry probe, a live cycle, a re-read of
both -- and the engine already had every callable needed to produce it. Measured on
the live tenant before this change: of the eight outstanding onboarding steps, ONE
could heal itself. These three were the cheapest to move.

THE SAFETY PROPERTY IS THE POINT, and it is what most of this file tests. Every one
of these heals produces its evidence by running a REAL sync, and the runbook warns on
nearly every step that a sync must never be triggered from the manager console --
"never Sync now from the manager console", "the credential lives on the box". Those
warnings were prose. The only thing enforcing them was that nobody had written the
button.

A self-heal IS that button. So writing one without a refusal would have converted the
mistake the runbook warns about into a one-click feature, which is a strictly worse
outcome than leaving the step manual. The refusal is therefore not a nicety around
the edge of the feature; it is the reason the feature is allowed to exist.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.lifecycle import edge_onboarding as eo

EDGE = "apps.schools.conversion_lock_state.deployment_is_edge_replica"
CYCLE = "apps.sync_engine.sync_runner.run_sync_cycle"
GATE = "apps.lifecycle.edge_onboarding.run_sync_gate"
LATEST = "apps.lifecycle.edge_onboarding._latest_sync_run"

HEALS = (
    "verify_and_sync_gate",
    "live_sync_proof",
    "go_dark_checklist",
)


def _school():
    return SimpleNamespace(id=1, pk=1, slug="gilead-tech", name="Gilead", country_code="CM")


def _run(ok=True, **kw):
    row = SimpleNamespace(ok=ok, conflicts=0, pushed=0, pulled=0, error="", message="")
    for k, v in kw.items():
        setattr(row, k, v)
    return row


class TheHealsMustRefuseOnTheCloudTests(SimpleTestCase):
    """The rule the runbook only ever stated in prose, made structural."""

    def _heal(self, key):
        step = next(s for s in eo.EDGE_ONBOARDING_STEPS if s.key == key)
        self.assertIsNotNone(step.self_heal, "%s has no self_heal" % key)
        return step.self_heal

    def test_every_one_of_them_refuses_when_this_is_not_a_box(self):
        with mock.patch(EDGE, return_value=False):
            for key in HEALS:
                ok, detail = self._heal(key)(_school())
                self.assertFalse(ok, "%s healed from the cloud" % key)
                self.assertIn("not the box", detail, key)

    def test_refusing_does_not_run_a_sync_at_all(self):
        # A refusal that still fires the cycle has refused nothing. This is the
        # assertion that actually protects the tenant.
        with mock.patch(EDGE, return_value=False), \
                mock.patch(CYCLE) as cycle, mock.patch(GATE) as gate:
            for key in HEALS:
                self._heal(key)(_school())
        cycle.assert_not_called()
        gate.assert_not_called()

    def test_it_asks_the_shared_helper_rather_than_re_reading_settings(self):
        # A second definition of "this is a box" is a second thing to drift, and the
        # two would disagree exactly once, silently, on some box nobody is watching.
        with mock.patch(EDGE, return_value=False) as helper:
            self._heal("live_sync_proof")(_school())
        helper.assert_called()

    def test_a_broken_host_check_refuses_rather_than_assuming_box(self):
        # Fail CLOSED. If we cannot tell where we are, running a sync is the one
        # option that can do harm.
        with mock.patch(EDGE, side_effect=RuntimeError("boom")):
            for key in HEALS:
                ok, detail = self._heal(key)(_school())
                self.assertFalse(ok, key)
                self.assertIn("could not determine", detail)


class TheGateHealRunsTheGateTests(SimpleTestCase):
    def test_it_clears_when_the_dry_probe_clears(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(GATE, return_value={"cleared": True, "detail": "probe ok", "run": {}}):
            ok, detail = eo._heal_verify_and_sync_gate(_school())
        self.assertTrue(ok)
        self.assertIn("probe ok", detail)

    def test_a_gate_that_says_no_is_reported_as_a_result_not_a_crash(self):
        # "We could not check" and "we checked and it is not ready" lead to
        # completely different next actions, so they must not read the same.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(GATE, return_value={"cleared": False, "detail": "operator unreachable", "run": {}}):
            ok, detail = eo._heal_verify_and_sync_gate(_school())
        self.assertFalse(ok)
        self.assertIn("ran and did NOT clear", detail)
        self.assertIn("operator unreachable", detail)
        self.assertIn("verify_edge_link", detail, "it should name the command that finds the FIRST break")


class TheLiveHealRespectsTheGateOrderingTests(SimpleTestCase):
    def test_it_refuses_without_a_cleared_dry_gate(self):
        # The gate exists so a live cycle is never the thing that discovers the
        # operator is unreachable -- and a failed LIVE row is what an operator reads
        # to decide whether this box converges at all.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=None), mock.patch(CYCLE) as cycle:
            ok, detail = eo._heal_live_sync_proof(_school())
        self.assertFalse(ok)
        self.assertIn("no cleared dry gate", detail)
        cycle.assert_not_called()

    def test_a_failed_dry_gate_also_blocks_it(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=False)), mock.patch(CYCLE) as cycle:
            ok, _ = eo._heal_live_sync_proof(_school())
        self.assertFalse(ok)
        cycle.assert_not_called()

    def test_it_runs_the_cycle_once_the_gate_has_cleared(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch(CYCLE, return_value={"ok": True, "pushed": 3, "pulled": 7, "conflicts": 0, "skipped": 0}) as cycle:
            ok, detail = eo._heal_live_sync_proof(_school())
        self.assertTrue(ok)
        self.assertEqual(cycle.call_args.kwargs["mode"], "live")
        self.assertIn("pushed=3", detail)
        self.assertIn("pulled=7", detail)

    def test_it_reports_rows_that_did_not_land(self):
        # A cycle that only says "pulled N" presents rows that did NOT apply as
        # success. `skipped` is the count nobody is being asked to resolve.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch(CYCLE, return_value={"ok": True, "pushed": 0, "pulled": 9, "conflicts": 0, "skipped": 4}):
            _ok, detail = eo._heal_live_sync_proof(_school())
        self.assertIn("skipped=4", detail)

    def test_an_upgrade_hold_is_not_reported_as_a_sync_failure(self):
        # It is the cloud's decision, not a fault here. Reporting it as a failure
        # sends somebody to debug a network that is working.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch(CYCLE, return_value={"ok": False, "held_for_upgrade": True, "upgrade_target": "2026.08.27"}):
            ok, detail = eo._heal_live_sync_proof(_school())
        self.assertFalse(ok)
        self.assertIn("held for an upgrade", detail)
        self.assertIn("not a fault here", detail)
        self.assertIn("2026.08.27", detail)


class TheGoDarkHealIsHonestAboutWhatItCannotDoTests(SimpleTestCase):
    """Two of its six parts are a machine's to fix. It must not imply otherwise."""

    def test_it_names_the_roster_rather_than_syncing_one(self):
        # Delta sync is not a bulk loader. Using it as one is the mistake this
        # runbook repeats a warning about on every data step.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch.object(eo, "_validate_live_sync_proof", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_go_dark_checklist", return_value=(False, "not cleared")), \
                mock.patch.object(eo, "_validate_seed_operational_data", return_value=(False, "empty")), \
                mock.patch.object(eo, "_validate_conversion_first_action", return_value=(True, "unlocked")):
            ok, detail = eo._heal_go_dark_checklist(_school())
        self.assertFalse(ok)
        self.assertIn("roster is empty", detail)
        self.assertIn("never a sync", detail)

    def test_it_names_the_conversion_lock_as_a_persons_job(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch.object(eo, "_validate_live_sync_proof", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_go_dark_checklist", return_value=(False, "not cleared")), \
                mock.patch.object(eo, "_validate_seed_operational_data", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_conversion_first_action", return_value=(False, "locked")):
            ok, detail = eo._heal_go_dark_checklist(_school())
        self.assertFalse(ok)
        self.assertIn("conversion is still locked", detail)
        self.assertIn("somebody must save", detail)

    def test_it_names_the_missing_backup(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch.object(eo, "_validate_live_sync_proof", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_go_dark_checklist", return_value=(False, "not cleared")), \
                mock.patch.object(eo, "_validate_seed_operational_data", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_conversion_first_action", return_value=(True, "unlocked")), \
                mock.patch.object(eo, "_validate_box_backup_verified", return_value=(False, "missing")):
            ok, detail = eo._heal_go_dark_checklist(_school())
        self.assertFalse(ok)
        self.assertIn("no verified box backup", detail)
        self.assertIn("box-backup.sh once", detail)

    def test_it_says_what_it_DID_do_even_when_it_ends_up_false(self):
        # A heal that quietly does two fifths of the work and returns a bare False is
        # indistinguishable from one that is broken.
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, side_effect=lambda s, mode=None: None if mode == "dry" else _run(ok=True)), \
                mock.patch(GATE, return_value={"cleared": True, "detail": "probe ok", "run": {}}), \
                mock.patch.object(eo, "_validate_live_sync_proof", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_go_dark_checklist", return_value=(False, "not cleared")), \
                mock.patch.object(eo, "_validate_seed_operational_data", return_value=(False, "empty")), \
                mock.patch.object(eo, "_validate_conversion_first_action", return_value=(True, "ok")):
            ok, detail = eo._heal_go_dark_checklist(_school())
        self.assertFalse(ok)
        self.assertIn("Ran:", detail)
        self.assertIn("dry gate cleared", detail)

    def test_it_passes_when_everything_is_genuinely_clear(self):
        with mock.patch(EDGE, return_value=True), \
                mock.patch(LATEST, return_value=_run(ok=True)), \
                mock.patch.object(eo, "_validate_live_sync_proof", return_value=(True, "ok")), \
                mock.patch.object(eo, "_validate_go_dark_checklist", return_value=(True, "cleared")):
            ok, detail = eo._heal_go_dark_checklist(_school())
        self.assertTrue(ok)
        self.assertIn("cleared", detail)


class NoHealMayRaiseTests(SimpleTestCase):
    """A heal that raises takes down the surface that called it."""

    def test_every_heal_on_every_step_survives_a_hostile_school(self):
        broken = SimpleNamespace()  # no id, no slug, no settings
        for step in eo.EDGE_ONBOARDING_STEPS:
            if step.self_heal is None:
                continue
            with mock.patch(EDGE, return_value=True), \
                    mock.patch(CYCLE, side_effect=RuntimeError("network gone")), \
                    mock.patch(GATE, side_effect=RuntimeError("gate exploded")):
                try:
                    ok, detail = step.self_heal(broken)
                except Exception as exc:  # noqa: BLE001
                    self.fail("%s raised %r" % (step.key, exc))
            self.assertIsInstance(ok, bool, step.key)
            self.assertIsInstance(detail, str, step.key)


class TheAutomationGapActuallyMovedTests(SimpleTestCase):
    def test_the_three_verification_steps_now_carry_heals(self):
        by_key = {s.key: s for s in eo.EDGE_ONBOARDING_STEPS}
        for key in HEALS:
            self.assertIsNotNone(by_key[key].self_heal, "%s still needs a person to type it" % key)

    def test_six_of_seventeen_steps_can_now_finish_themselves(self):
        # The measure the whole exercise is aimed at. If a later change drops one,
        # this is the number that should make somebody look.
        healable = [s.key for s in eo.EDGE_ONBOARDING_STEPS if s.self_heal is not None]
        self.assertEqual(
            len(healable), 6, "healable steps changed: %s" % sorted(healable)
        )
