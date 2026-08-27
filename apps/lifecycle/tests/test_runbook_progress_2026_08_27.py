"""The runbook had no idea which of its own steps were done.

`generate_runbook` returned key/title/purpose/command and nothing about STATE, while
`run_verification_suite` already ran every step's validate() and returned exactly the
{key, ok, detail} a checklist needs. Two functions, both correct, never joined -- so a
school read a flat wall of seventeen commands with no way to tell step 3 from step 14,
and no way to see that six of them were already finished.

WHY `healable_todo` IS THE NUMBER THAT MATTERS. A percentage bar cannot distinguish
"nine steps left, the wizard can do all nine" from "nine steps left, every one needs
somebody who knows what a terminal is". Those are the same bar and completely
different products. The count of outstanding steps that can self-heal is the actual
measure of how close this is to something a school can run alone, so the progress
block reports it beside the percentage rather than leaving it to be inferred.

Mocked suite throughout: these assert the JOIN and the arithmetic, which is where the
bugs would be. Whether an individual validate() is correct is that validator's own
test, and running seventeen of them here would make this file slow and flaky for no
extra coverage.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.lifecycle import edge_onboarding as eo

SUITE = "apps.lifecycle.edge_onboarding.run_verification_suite"


def _school(slug="gilead-tech"):
    return SimpleNamespace(id=1, pk=1, slug=slug, name="Gilead Tech", country="CM")


def _suite(rows):
    return {
        "steps": rows,
        "ok": all(r.get("ok") for r in rows),
        "passed": sum(1 for r in rows if r.get("ok")),
        "total": len(rows),
        "skipped": sum(1 for r in rows if r.get("skipped")),
        "evaluated": sum(1 for r in rows if not r.get("skipped")),
    }


def _all(status_for):
    """A suite row for every step, driven by a key -> outcome callable."""
    rows = []
    for step in eo.EDGE_ONBOARDING_STEPS:
        outcome = status_for(step)
        if outcome is None:
            continue  # absent from the preview entirely
        rows.append({"key": step.key, **outcome})
    return _suite(rows)


class TheRunbookStillWorksWithoutStatusTests(SimpleTestCase):
    """The default must not change: existing callers render a plain runbook."""

    def test_no_status_keys_are_added_by_default(self):
        book = eo.generate_runbook(_school())
        self.assertNotIn("progress", book)
        for entry in book["steps"]:
            self.assertNotIn("status", entry)
            self.assertNotIn("can_self_heal", entry)

    def test_the_default_does_not_run_a_single_check(self):
        # Rendering a runbook must stay cheap. If this ever starts validating by
        # default, every page that lists the steps pays for seventeen checks.
        with mock.patch(SUITE) as suite:
            eo.generate_runbook(_school())
        suite.assert_not_called()


class EveryStepCarriesItsOwnStatusTests(SimpleTestCase):
    def test_each_step_gains_status_detail_and_healability(self):
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": "fine"})):
            book = eo.generate_runbook(_school(), with_status=True)
        self.assertEqual(len(book["steps"]), len(eo.EDGE_ONBOARDING_STEPS))
        for entry in book["steps"]:
            self.assertIn(entry["status"], {
                eo.STATUS_DONE, eo.STATUS_TODO, eo.STATUS_SKIPPED, eo.STATUS_NOT_CHECKED,
            })
            self.assertIn("detail", entry)
            self.assertIsInstance(entry["can_self_heal"], bool)

    def test_healability_is_read_from_the_step_not_guessed(self):
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})):
            book = eo.generate_runbook(_school(), with_status=True)
        by_key = {e["key"]: e for e in book["steps"]}
        for step in eo.EDGE_ONBOARDING_STEPS:
            self.assertEqual(by_key[step.key]["can_self_heal"], step.self_heal is not None)

    def test_a_step_absent_from_the_preview_is_NOT_CHECKED_not_TODO(self):
        # The distinction this whole status vocabulary exists for. A box-side check
        # rendered on the cloud has not failed -- it has not been asked. Calling it
        # TODO tells somebody to redo work that may already be finished.
        first = eo.EDGE_ONBOARDING_STEPS[0]
        suite = _all(lambda s: None if s.key == first.key else {"ok": True, "detail": ""})
        with mock.patch(SUITE, return_value=suite):
            book = eo.generate_runbook(_school(), with_status=True)
        entry = next(e for e in book["steps"] if e["key"] == first.key)
        self.assertEqual(entry["status"], eo.STATUS_NOT_CHECKED)
        self.assertIn("box-side state", entry["detail"])
        self.assertIn("gilead-tech", entry["detail"], "the command should name the school")

    def test_a_skipped_row_stays_skipped(self):
        first = eo.EDGE_ONBOARDING_STEPS[0]
        suite = _all(
            lambda s: {"ok": False, "skipped": True, "detail": "manager host"}
            if s.key == first.key
            else {"ok": True, "detail": ""}
        )
        with mock.patch(SUITE, return_value=suite):
            book = eo.generate_runbook(_school(), with_status=True)
        entry = next(e for e in book["steps"] if e["key"] == first.key)
        self.assertEqual(entry["status"], eo.STATUS_SKIPPED)


class TheProgressBlockTests(SimpleTestCase):
    def test_the_counts_add_up_to_the_step_count(self):
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})):
            p = eo.generate_runbook(_school(), with_status=True)["progress"]
        self.assertEqual(
            p["done"] + p["todo"] + p["skipped"] + p["not_checked"], p["total"]
        )
        self.assertEqual(p["total"], len(eo.EDGE_ONBOARDING_STEPS))

    def test_everything_done_is_a_hundred_percent(self):
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})):
            p = eo.generate_runbook(_school(), with_status=True)["progress"]
        self.assertEqual(p["percent"], 100)
        self.assertEqual(p["todo"], 0)
        self.assertEqual(p["needs_a_person"], 0)

    def test_percent_is_floored_so_it_never_reads_100_with_work_left(self):
        # 16 of 17 is 94.1%. Rounding would show 94; the danger is the other end --
        # any rounding UP that reaches 100 while a step is outstanding makes the bar
        # a liar at exactly the moment somebody stops reading it.
        last = eo.EDGE_ONBOARDING_STEPS[-1]
        suite = _all(
            lambda s: {"ok": s.key != last.key, "detail": ""}
        )
        with mock.patch(SUITE, return_value=suite):
            p = eo.generate_runbook(_school(), with_status=True)["progress"]
        self.assertEqual(p["todo"], 1)
        self.assertLess(p["percent"], 100)

    def test_healable_todo_counts_only_outstanding_steps_that_can_fix_themselves(self):
        # Nothing done. Every step outstanding. The healable count must equal the
        # number of steps that actually carry a self_heal -- that is the number a
        # school can clear without help.
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": False, "detail": "no"})):
            p = eo.generate_runbook(_school(), with_status=True)["progress"]
        expected = sum(1 for s in eo.EDGE_ONBOARDING_STEPS if s.self_heal is not None)
        self.assertEqual(p["healable_todo"], expected)
        self.assertEqual(p["needs_a_person"], p["todo"] - expected)

    def test_a_done_step_is_never_counted_as_healable(self):
        # It would inflate the one number that is supposed to measure remaining work.
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})):
            p = eo.generate_runbook(_school(), with_status=True)["progress"]
        self.assertEqual(p["healable_todo"], 0)

    def test_progress_is_computable_from_the_steps_alone(self):
        # The block and the list must not be able to disagree: a surface that renders
        # "6 of 17" above a list showing seven ticks is worse than showing neither.
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})):
            book = eo.generate_runbook(_school(), with_status=True)
        self.assertEqual(eo.runbook_progress(book["steps"]), book["progress"])


class ItMustNotLookLikeSomebodyRanTheLiveGateTests(SimpleTestCase):
    def test_the_read_only_preview_is_what_runs(self):
        # include_gate=True runs the live dry sync and records an EdgeSyncRun. A page
        # render must never do that -- the operator's own gate result would then be
        # indistinguishable from a side effect of somebody opening a tab.
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})) as suite:
            eo.generate_runbook(_school(), with_status=True)
        suite.assert_called_once()
        self.assertIs(suite.call_args.kwargs["include_gate"], False)

    def test_host_kind_is_passed_through(self):
        # So a manager-host render marks box-side checks skipped rather than failed.
        with mock.patch(SUITE, return_value=_all(lambda s: {"ok": True, "detail": ""})) as suite:
            eo.generate_runbook(_school(), with_status=True, host_kind="manager")
        self.assertEqual(suite.call_args.kwargs["host_kind"], "manager")
