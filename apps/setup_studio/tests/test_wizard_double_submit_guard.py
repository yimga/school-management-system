"""apply_step_answer double-submit guard.

A wizard step re-submitted with a byte-identical answer (double-click, retry,
network replay) must NOT re-run its persistence writer — that is how
create-style writers (student/teacher onboarding, field-trip consent) produce
duplicate rows. A genuinely changed answer still re-runs the writer.

Uses a synthetic single-step wizard whose writer counts its invocations, so the
test asserts the side-effect count directly rather than reaching into any real
domain model.
"""

from __future__ import annotations

from pathlib import Path

from django.test import TestCase

from apps.schools.models import School
from apps.setup_studio import wizard_engine, wizard_state_resolver

# Module-level so the dotted writer path resolves to a real, importable callable.
_WRITER_CALLS: list[dict] = []


def _counting_writer(*, school, wizard_key, step_key, payload, actor_user_id=None):
    _WRITER_CALLS.append({"step": step_key, "value": payload.get("value")})


_PROBE_KEY = "double_submit_probe"
_PROBE_SPEC = {
    "wizard_key": _PROBE_KEY,
    "version": 1,
    "audience": ["operator"],
    "steps": [
        {
            "key": "only",
            "input_type": "text",
            "validation": {"required": True},
            "persistence": {
                "target": "custom",
                "writer": (
                    "apps.setup_studio.tests.test_wizard_double_submit_guard"
                    "::_counting_writer"
                ),
            },
        },
    ],
}


class DoubleSubmitGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Double Submit School",
            slug="double-submit",
            subdomain="double-submit",
            is_active=True,
        )

    def setUp(self):
        _WRITER_CALLS.clear()
        parsed = wizard_engine._parse_wizard(_PROBE_SPEC, Path("/tmp/double_submit_probe.json"))
        wizard_engine.WIZARD_REGISTRY[_PROBE_KEY] = parsed

    def tearDown(self):
        wizard_engine.WIZARD_REGISTRY.pop(_PROBE_KEY, None)
        wizard_state_resolver.reset_wizard(self.school, _PROBE_KEY)

    def _apply(self, value):
        return wizard_state_resolver.apply_step_answer(
            self.school, _PROBE_KEY, "only", {"value": value},
        )

    def test_first_submit_runs_writer(self):
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        self._apply("x")
        self.assertEqual(len(_WRITER_CALLS), 1)

    def test_identical_resubmit_skips_writer(self):
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        self._apply("x")
        self._apply("x")  # double-click / replay — identical payload
        self.assertEqual(
            len(_WRITER_CALLS), 1,
            "identical re-submit of a completed step must not re-run the writer",
        )

    def test_changed_resubmit_reruns_writer(self):
        wizard_state_resolver.start_wizard(self.school, _PROBE_KEY)
        self._apply("x")
        self._apply("y")  # genuine edit — must persist the change
        self.assertEqual(
            len(_WRITER_CALLS), 2,
            "a changed answer must re-run the writer (edit is legitimate)",
        )
        self.assertEqual(_WRITER_CALLS[-1]["value"], "y")
