"""SimpleTestCase coverage for the offline person-creation handler (no DB).

The full create path is DB-backed (CI). Here we lock down the security gate —
authorization is RE-DERIVED server-side and a non-authorized / unknown offline
user can never create a student/teacher/applicant via the offline rail — the
cross-tenant FK guard, and the workflow routing.
"""
from __future__ import annotations

from types import SimpleNamespace
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

    def test_workflow_names_are_recognized(self):
        from apps.people.offline_workflow_handlers import PEOPLE_WORKFLOWS

        self.assertIn("people_student_create", PEOPLE_WORKFLOWS)
        self.assertIn("people_teacher_create", PEOPLE_WORKFLOWS)
        self.assertIn("people_applicant_create", PEOPLE_WORKFLOWS)


class TeacherOfflineCreateTests(SimpleTestCase):
    def test_blocks_unauthorized_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_user_can_add_teacher", return_value=(mock.MagicMock(), False)
        ):
            out = h.apply_people_workflow(
                7, 5, "people_teacher_create",
                {"email": "t@example.com", "password": "x"}, {},
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_authorized_to_create_teacher")

    def test_blocks_unknown_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_user_can_add_teacher", return_value=(None, False)
        ):
            out = h.apply_people_workflow(
                7, 999, "people_teacher_create", {"email": "t@example.com"}, {},
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_user")


class ApplicantOfflineCreateTests(SimpleTestCase):
    def test_blocks_unauthorized_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_user_can_add_applicant", return_value=(mock.MagicMock(), False)
        ):
            out = h.apply_people_workflow(
                7, 5, "people_applicant_create",
                {"first_name": "A", "last_name": "B", "email": "a@example.com"}, {},
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_authorized_to_create_applicant")

    def test_blocks_unknown_user(self):
        import apps.people.offline_workflow_handlers as h

        with mock.patch.object(
            h, "_user_can_add_applicant", return_value=(None, False)
        ):
            out = h.apply_people_workflow(
                7, 999, "people_applicant_create", {"first_name": "A"}, {},
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_user")


class CrossTenantFkGuardTests(SimpleTestCase):
    """The offline drain has no request RLS, so a forged FK id from another
    tenant must be rejected by the writer itself."""

    def test_rejects_fk_from_foreign_tenant(self):
        from apps.people.offline_workflow_handlers import _reject_cross_tenant_fks

        foreign = SimpleNamespace(school_id="tenant-B")
        form = SimpleNamespace(cleaned_data={"classroom": foreign})
        out = _reject_cross_tenant_fks(form, "tenant-A", ("classroom",))
        self.assertEqual(out, {"ok": False, "error": "cross_tenant_classroom"})

    def test_allows_fk_from_same_tenant(self):
        from apps.people.offline_workflow_handlers import _reject_cross_tenant_fks

        same = SimpleNamespace(school_id="tenant-A")
        form = SimpleNamespace(cleaned_data={"department": same})
        self.assertIsNone(
            _reject_cross_tenant_fks(form, "tenant-A", ("department",))
        )

    def test_allows_absent_or_schoolless_fk(self):
        from apps.people.offline_workflow_handlers import _reject_cross_tenant_fks

        form = SimpleNamespace(cleaned_data={"reports_to": None})
        self.assertIsNone(
            _reject_cross_tenant_fks(form, "tenant-A", ("reports_to",))
        )
