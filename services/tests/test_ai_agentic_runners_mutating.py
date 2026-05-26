"""Wave Q3 (v3.95.2 — 2026-05-26) — Mutating agentic AI runner tests.

These runners are intentionally NOT auto-registered. Tests confirm:
1. Importing the module doesn't mutate any global registry.
2. Each runner refuses when params are missing or tenant scope unavailable.
3. The opt-in lookup table maps 3 known mutating actions.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from services.ai_agentic import ActionContext, ProposedAction
from services.ai_agentic_runners import _RUNNERS
from services.ai_agentic_runners_mutating import (
    OPT_IN_MUTATING_RUNNERS,
    run_mark_student_absent,
    run_schedule_parent_callback,
    run_send_parent_message,
)


def _ctx(**kw):
    defaults = dict(
        tenant_id="t1", user_id="u1", user_roles=("ADMIN",),
        confirmed_by="u1",
    )
    defaults.update(kw)
    return ActionContext(**defaults)


class GateInvariantTests(SimpleTestCase):
    """Importing this module must NOT add anything to the auto-runner table."""

    def test_module_import_does_not_register_mutating_runners(self):
        # The Wave P-B runner registry holds only read-only.
        for name in ("send_parent_message", "mark_student_absent",
                      "schedule_parent_callback", "apply_fee_waiver",
                      "purge_student_record"):
            self.assertNotIn(name, _RUNNERS)

    def test_opt_in_lookup_holds_three_runners(self):
        self.assertIn("send_parent_message", OPT_IN_MUTATING_RUNNERS)
        self.assertIn("mark_student_absent", OPT_IN_MUTATING_RUNNERS)
        self.assertIn("schedule_parent_callback", OPT_IN_MUTATING_RUNNERS)


class SendParentMessageTests(SimpleTestCase):

    def test_missing_params(self):
        result = run_send_parent_message(
            ProposedAction(action="send_parent_message", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_missing_tenant_school(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_send_parent_message(
                ProposedAction(
                    action="send_parent_message",
                    params={"parent_id": "1", "channel": "whatsapp",
                            "body": "Hello"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])


class MarkStudentAbsentTests(SimpleTestCase):

    def test_missing_student_id(self):
        result = run_mark_student_absent(
            ProposedAction(action="mark_student_absent", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_invalid_date_format(self):
        result = run_mark_student_absent(
            ProposedAction(
                action="mark_student_absent",
                params={"student_id": "1", "date": "not-a-date"},
            ),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("invalid date", result["error"])

    def test_tenant_unavailable(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_mark_student_absent(
                ProposedAction(
                    action="mark_student_absent",
                    params={"student_id": "1"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])


class ScheduleParentCallbackTests(SimpleTestCase):

    def test_missing_parent_id(self):
        result = run_schedule_parent_callback(
            ProposedAction(action="schedule_parent_callback", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_tenant_unavailable(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_schedule_parent_callback(
                ProposedAction(
                    action="schedule_parent_callback",
                    params={"parent_id": "1"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])
