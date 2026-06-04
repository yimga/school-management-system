"""SimpleTestCase coverage for the offline person-creation handler (no DB).

The full create path is DB-backed (CI). Here we lock down the security gate —
authorization is RE-DERIVED server-side and a non-authorized / unknown offline
user can never create a student via the offline rail — and the workflow routing.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase


class PeopleOfflineWorkflowRoutingTests(SimpleTestCase):
    def test_unknown_workflow_returns_none(self):
        from apps.people.offline_workflow_handlers import apply_people_workflow

        self.assertIsNone(apply_people_workflow(1, 1, "finance_cash_closure", {}, {}))
        self.assertIsNone(apply_people_workflow(1, 1, "", {}, {}))

    def test_student_create_blocks_unauthorized_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_user_can_add_student", return_value=(mock.MagicMock(), False)
        ):
            out = h.apply_people_workflow(
                7, 5, "people_student_create", {"first_name": "A", "last_name": "B"}, {}
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_authorized_to_create_student")

    def test_student_create_blocks_unknown_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(h, "_user_can_add_student", return_value=(None, False)):
            out = h.apply_people_workflow(
                7, 999, "people_student_create", {"first_name": "A", "last_name": "B"}, {}
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_user")

    def test_workflow_name_is_recognized(self):
        from apps.people.offline_workflow_handlers import PEOPLE_WORKFLOWS

        self.assertIn("people_student_create", PEOPLE_WORKFLOWS)
