"""A refused wizard step must say why.

Raising ``WizardError`` on a failed persistence writer stopped the wizard
reporting success it had not earned, but the operator still got nothing: both
view handlers rebuild ``errors`` by RE-VALIDATING the submitted payload, and a
payload that validated and then failed to PERSIST produces no field errors at
all. The writer's reason went to the log and the step re-rendered unchanged.

Two things are covered here:

* ``step_error`` -- the non-field reason, carried out of the writer on the
  exception as ``operator_message``.
* ``unrendered_errors`` -- field errors for the 4 of 19 input partials that
  render none of their own (they use fixed field names instead of a field
  loop). 11 of the 146 registered steps use one of those.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase

from apps.schools.models import School
from apps.setup_studio import wizard_engine, wizard_state_resolver
from apps.setup_studio.wizard_views import (
    _INPUTS_RENDERING_OWN_FIELD_ERRORS,
    _step_error_message,
)

INPUTS_DIR = (
    Path(__file__).resolve().parents[3] / "templates" / "setup_studio" / "inputs"
)

# Module-level so the dotted writer path resolves to a real, importable callable.
_RAISED_MESSAGE = "End date must fall after the start date."


def _failing_writer(*, school, wizard_key, step_key, payload, actor_user_id=None):
    raise ValueError(_RAISED_MESSAGE)


def _silent_writer(*, school, wizard_key, step_key, payload, actor_user_id=None):
    raise ValueError("   ")  # whitespace only -> no usable operator message


class _FakeStep:
    """Only what wizard_step_body.html touches: it selects an input partial by
    input_type and otherwise passes the context straight through."""

    key = "only"
    input_type = "text"
    label = "Only"
    help_text = ""
    validation: dict = {}
    options: list = []


class _FakeWizard:
    wizard_key = "step_error_probe"


_PROBE_KEY = "step_error_probe"
_SILENT_KEY = "step_error_silent_probe"


def _spec(key: str, writer: str) -> dict:
    return {
        "wizard_key": key,
        "version": 1,
        "audience": ["operator"],
        "steps": [
            {
                "key": "only",
                "input_type": "text",
                "validation": {"required": True},
                "persistence": {"target": "custom", "writer": writer},
            }
        ],
    }


class StepErrorMessageTests(SimpleTestCase):
    """The banner text itself. No DB, no templates."""

    def test_writer_reason_is_shown_when_there_are_no_field_errors(self):
        exc = wizard_engine.WizardError("persistence writer failed for a.b: boom")
        exc.operator_message = "End date must fall after the start date."
        message = _step_error_message(exc, {})
        self.assertIn("End date must fall after the start date.", message)
        self.assertIn("not saved", message)
        # The log-shaped wrapper must never reach a person.
        self.assertNotIn("persistence writer failed", message)
        self.assertNotIn("a.b", message)

    def test_generic_message_when_the_cause_is_not_actionable(self):
        exc = wizard_engine.WizardError("persistence writer could not be loaded")
        exc.operator_message = None
        message = _step_error_message(exc, {})
        self.assertIn("not saved", message)
        self.assertIn("nothing was changed", message)

    def test_no_banner_when_field_errors_already_render(self):
        """A banner here would just repeat what is already under each input."""
        exc = wizard_engine.WizardError("nope")
        exc.operator_message = "should not surface"
        self.assertEqual(_step_error_message(exc, {"name": "wizards.errors.required"}), "")

    def test_exception_without_the_attribute_still_produces_a_message(self):
        self.assertIn("not saved", _step_error_message(ValueError("raw"), {}))


class InputPartialErrorContractTests(SimpleTestCase):
    """Seal: the constant must keep matching the templates.

    If a new input partial renders its own field errors and is not listed, the
    step region duplicates the message. If a listed one STOPS rendering them,
    the message disappears entirely. Both are caught here.
    """

    #: An output tag, not the bare word. A partial that merely MENTIONS errors
    #: (a comment, an attribute name) renders none, and counting it as
    #: self-rendering would argue for dropping its step-region coverage.
    _RENDERS_ERRORS = re.compile(r"{{-?\s*errors[.|\s}]")

    def _self_rendering(self) -> set[str]:
        return {
            f.stem
            for f in INPUTS_DIR.glob("*.html")
            if self._RENDERS_ERRORS.search(f.read_text(encoding="utf-8"))
        }

    def test_constant_matches_the_templates(self):
        self.assertEqual(set(_INPUTS_RENDERING_OWN_FIELD_ERRORS), self._self_rendering())

    def test_the_error_blind_partials_are_covered_by_the_step_region(self):
        blind = {f.stem for f in INPUTS_DIR.glob("*.html")} - self._self_rendering()
        # Named explicitly so a change to this set is a visible diff, not a drift.
        self.assertEqual(
            blind, {"csv_mapping", "duration", "key_value_pairs", "ranked_list"}
        )
        for name in blind:
            self.assertNotIn(name, _INPUTS_RENDERING_OWN_FIELD_ERRORS)

    def _render(self, **ctx) -> str:
        """Render the step body for real.

        A substring check on the SOURCE is not enough: the
        {% if step_error or unrendered_errors %} guard itself contains the word
        "step_error", so grepping for it stays green even when the paragraph
        that prints the value is deleted. Only the output proves it.
        """
        base = {
            "step": _FakeStep(),
            "wizard": _FakeWizard(),
            "errors": {},
            "answers": {},
        }
        return render_to_string(
            "setup_studio/partials/wizard_step_body.html", {**base, **ctx}
        )

    def test_the_writer_reason_reaches_the_page(self):
        html = self._render(step_error="Term end must fall after the start.")
        self.assertIn("Term end must fall after the start.", html)
        self.assertIn("data-rmc-wizard-step-error", html)
        self.assertIn('role="alert"', html)

    def test_field_errors_for_blind_partials_reach_the_page(self):
        html = self._render(
            unrendered_errors=["Column 3 is not a date.", "Row 9 is empty."]
        )
        self.assertIn("Column 3 is not a date.", html)
        self.assertIn("Row 9 is empty.", html)
        self.assertIn("data-rmc-wizard-step-error", html)

    def test_no_region_when_the_step_is_clean(self):
        # An always-on empty banner would be its own bug.
        html = self._render()
        self.assertNotIn("data-rmc-wizard-step-error", html)
        self.assertNotIn("rmc-banner--error", html)

    def test_the_reason_is_escaped(self):
        # The reason originates in a writer's exception text, which can carry
        # whatever a payload put there.
        html = self._render(step_error="<img src=x onerror=alert(1)>")
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img", html)


class WriterFailureCarriesItsReasonTests(TestCase):
    """End to end through apply_step_answer, on a synthetic wizard."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Step Error School",
            slug="step-error",
            subdomain="step-error",
            is_active=True,
        )

    def setUp(self):
        base = "apps.setup_studio.tests.test_wizard_step_error_surface"
        for key, writer in (
            (_PROBE_KEY, f"{base}::_failing_writer"),
            (_SILENT_KEY, f"{base}::_silent_writer"),
        ):
            wizard_engine.WIZARD_REGISTRY[key] = wizard_engine._parse_wizard(
                _spec(key, writer), Path(f"/tmp/{key}.json")
            )

    def tearDown(self):
        for key in (_PROBE_KEY, _SILENT_KEY):
            wizard_engine.WIZARD_REGISTRY.pop(key, None)
            wizard_state_resolver.reset_wizard(self.school, key)

    def test_writer_reason_rides_out_on_the_exception(self):
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        with self.assertRaises(wizard_engine.WizardError) as caught:
            wizard_state_resolver.apply_step_answer(
                self.school, _PROBE_KEY, "only", {"value": "x"}
            )
        self.assertEqual(caught.exception.operator_message, _RAISED_MESSAGE)

    def test_whitespace_only_reason_becomes_no_reason(self):
        wizard_state_resolver.start_wizard(self.school, _SILENT_KEY)
        with self.assertRaises(wizard_engine.WizardError) as caught:
            wizard_state_resolver.apply_step_answer(
                self.school, _SILENT_KEY, "only", {"value": "x"}
            )
        self.assertIsNone(caught.exception.operator_message)

    def test_the_step_is_still_not_marked_complete(self):
        """The original defect. Guarded here as well as at its own test."""
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        with self.assertRaises(wizard_engine.WizardError):
            wizard_state_resolver.apply_step_answer(
                self.school, _PROBE_KEY, "only", {"value": "x"}
            )
        state = wizard_state_resolver.get_wizard_state(self.school, _PROBE_KEY)
        self.assertNotIn("only", state.get("completed") or [])

    def test_the_message_a_person_sees_is_built_from_that_reason(self):
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        with self.assertRaises(wizard_engine.WizardError) as caught:
            wizard_state_resolver.apply_step_answer(
                self.school, _PROBE_KEY, "only", {"value": "x"}
            )
        # Exactly what the view handler does with it.
        self.assertIn(_RAISED_MESSAGE, _step_error_message(caught.exception, {}))
