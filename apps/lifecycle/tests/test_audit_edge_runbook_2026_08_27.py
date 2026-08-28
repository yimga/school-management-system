"""The audit reports 0 FAIL. These prove that means something.

A gate nobody has seen fire is indistinguishable from a gate that cannot fire, and
this repo has shipped at least one scan that reported zero because it was broken. So
every check gets a planted defect and has to catch it.

The audit answers the question a runbook cannot answer about itself: it is DATA that
describes actions, so it is only correct while those actions still exist. A step
naming a management command renamed two waves ago fails no test, because there is no
test -- until this one.
"""

from __future__ import annotations

import dataclasses
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.lifecycle import edge_onboarding as eo

STEPS = "apps.lifecycle.edge_onboarding.EDGE_ONBOARDING_STEPS"


def _run(steps=None):
    out = StringIO()
    if steps is None:
        call_command("audit_edge_runbook", stdout=out)
    else:
        with mock.patch(STEPS, tuple(steps)):
            call_command("audit_edge_runbook", stdout=out)
    return out.getvalue()


def _clone(step, **changes):
    return dataclasses.replace(step, **changes)


class TheCleanTreePassesTests(SimpleTestCase):
    def test_the_real_runbook_is_sound(self):
        body = _run()
        self.assertIn("0 FAIL", body)
        self.assertIn("internally sound", body)

    def test_it_actually_inspected_all_seventeen_steps(self):
        # A pass over an empty list also reports 0 FAIL.
        body = _run()
        self.assertIn("%d steps" % len(eo.EDGE_ONBOARDING_STEPS), body)
        self.assertIn("6 of 17 steps carry a self-heal", body)


class EveryCheckMustFireTests(SimpleTestCase):
    """One planted defect per check. If any of these passes, that check is dead."""

    def setUp(self):
        self.first = eo.EDGE_ONBOARDING_STEPS[0]

    def test_A_catches_a_command_that_does_not_exist(self):
        # The most common way a runbook rots: a command renamed two waves ago.
        broken = _clone(self.first, command_template="python manage.py no_such_command_xyz")
        body = _run([broken])
        self.assertIn("DOES NOT EXIST", body)
        self.assertIn("1 FAIL", body)

    def test_A_does_not_flag_a_command_that_does_exist(self):
        good = _clone(self.first, command_template="python manage.py migrate")
        body = _run([good])
        self.assertIn("0 FAIL", body)

    def test_C_catches_a_missing_help_doc(self):
        broken = _clone(self.first, help_doc="docs/THIS_DOC_DOES_NOT_EXIST.md")
        body = _run([broken])
        self.assertIn("IS MISSING", body)
        self.assertIn("1 FAIL", body)

    def test_D_catches_a_validator_that_raises(self):
        def _explodes(school):
            raise RuntimeError("boom")

        broken = _clone(self.first, validate=_explodes, command_template="", help_doc="")
        body = _run([broken])
        self.assertIn("validate RAISED RuntimeError", body)

    def test_D_catches_a_validator_returning_the_wrong_shape(self):
        # A validator returning a bare bool passes `if ok:` at every call site and
        # then blows up wherever the detail is read.
        broken = _clone(
            self.first, validate=lambda s: True, command_template="", help_doc=""
        )
        body = _run([broken])
        self.assertIn("not (bool, str)", body)

    def test_E_catches_a_heal_that_raises(self):
        def _explodes(school):
            raise RuntimeError("boom")

        broken = _clone(
            self.first, self_heal=_explodes, command_template="", help_doc=""
        )
        body = _run([broken])
        self.assertIn("heal RAISED RuntimeError", body)

    def test_F_catches_a_heal_no_bring_up_path_routes(self):
        # cloud_preview=False keeps it out of the verification loop, and a key the
        # explicit phase does not name is reachable only from a console call.
        orphan = _clone(
            self.first,
            key="orphan_step",
            self_heal=lambda s: (True, "ok"),
            cloud_preview=False,
            command_template="",
            help_doc="",
            named_url_name="",
        )
        body = _run([orphan])
        self.assertIn("no bring-up path routes this heal", body)

    def test_G_catches_duplicate_keys(self):
        twin = _clone(self.first, command_template="", help_doc="", named_url_name="")
        body = _run([twin, twin])
        self.assertIn("duplicate step keys", body)

    def test_G_catches_missing_prose(self):
        blank = _clone(
            self.first, workaround="", command_template="", help_doc="", named_url_name=""
        )
        body = _run([blank])
        self.assertIn("workaround is empty", body)


class ItMustNotChangeAnythingTests(SimpleTestCase):
    """It runs on a live box. That is the point, and it is also the constraint."""

    def test_it_calls_validators_with_a_school_that_has_no_fields(self):
        # Never a real tenant: a validator handed a live school could write, and an
        # audit that changes the thing it measures is worse than no audit.
        seen = []

        def _record(school):
            seen.append(school)
            return True, "ok"

        step = _clone(
            eo.EDGE_ONBOARDING_STEPS[0],
            validate=_record,
            command_template="",
            help_doc="",
            named_url_name="",
        )
        _run([step])
        self.assertTrue(seen)
        for school in seen:
            self.assertIsInstance(school, SimpleNamespace)
            self.assertFalse(getattr(school, "pk", None))

    def test_a_heal_is_invoked_but_only_against_that_empty_school(self):
        seen = []
        step = _clone(
            eo.EDGE_ONBOARDING_STEPS[0],
            self_heal=lambda s: (seen.append(s), (True, "ok"))[1],
            command_template="",
            help_doc="",
            named_url_name="",
        )
        _run([step])
        self.assertTrue(seen)
        self.assertFalse(getattr(seen[0], "pk", None))


class StrictModeTests(SimpleTestCase):
    def test_strict_exits_nonzero_on_a_defect(self):
        broken = _clone(
            eo.EDGE_ONBOARDING_STEPS[0],
            command_template="python manage.py no_such_command_xyz",
        )
        with mock.patch(STEPS, (broken,)):
            with self.assertRaises(SystemExit):
                call_command("audit_edge_runbook", "--strict", stdout=StringIO())

    def test_strict_is_silent_on_a_clean_tree(self):
        # It must be usable as a pre-rebuild gate, which means green has to be quiet.
        call_command("audit_edge_runbook", "--strict", stdout=StringIO())
