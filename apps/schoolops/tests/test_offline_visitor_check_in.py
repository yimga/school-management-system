"""SimpleTestCase coverage for the offline visitor check-in handler (no DB).

Locks the authorization gate (re-derived server-side) and the workflow routing.
The full create path is DB-backed (CI). Also documents — by omission — that this
is the ONLY ops surface wired offline (clinic is read-only; library/transport are
stateful shared-resource writes kept online to avoid double-issue conflicts).
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase


class SchoolopsWorkflowRoutingTests(SimpleTestCase):
    def test_unknown_workflow_returns_none(self):
        from apps.schoolops.offline_workflow_handlers import apply_schoolops_workflow

        self.assertIsNone(apply_schoolops_workflow(1, 1, "library_loan", {}, {}))
        self.assertIsNone(apply_schoolops_workflow(1, 1, "", {}, {}))

    def test_workflow_set_is_visitor_only(self):
        from apps.schoolops.offline_workflow_handlers import SCHOOLOPS_WORKFLOWS

        self.assertEqual(SCHOOLOPS_WORKFLOWS, frozenset({"visitor_check_in"}))


class VisitorCheckInAuthzTests(SimpleTestCase):
    def test_blocks_unauthorized_user(self):
        import apps.schoolops.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_resolve_actor", return_value=(mock.MagicMock(), False)
        ):
            out = h.apply_schoolops_workflow(
                7, 5, "visitor_check_in", {"visitor_name": "Jane"}, {}
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_authorized_visitor_log")

    def test_blocks_unknown_user(self):
        import apps.schoolops.offline_workflow_handlers as h

        with mock.patch.object(h, "_resolve_actor", return_value=(None, False)):
            out = h.apply_schoolops_workflow(
                7, 999, "visitor_check_in", {"visitor_name": "Jane"}, {}
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_user")

    def test_requires_visitor_name(self):
        import apps.schoolops.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_resolve_actor", return_value=(mock.MagicMock(), True)
        ):
            out = h.apply_schoolops_workflow(
                7, 5, "visitor_check_in", {"visitor_name": "   "}, {}
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "visitor_name_required")
