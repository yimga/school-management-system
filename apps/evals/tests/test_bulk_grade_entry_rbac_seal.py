"""Regression seal: BulkGradeEntryView must be gated to mark-editing roles.

Bug (2026-06-17 gap analysis): the view was decorated with ``login_required`` only, so
ANY authenticated tenant user — including STUDENT or PARENT — could POST bulk mutations
to Evaluation score fields. Fix added
``role_required(ADMIN, HOD, TEACHER, "HEAD_OF_ACADEMICS")``.

Hermetic (no DB): the role helpers are patched to their real contract so the test does
not depend on the local test DB. The deny path is exercised through the REAL view (the
role gate rejects before the DB-touching GET body); the admit path is checked on a dummy
view carrying the identical gate.
"""
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.evals.views_bulk_grade_entry import BulkGradeEntryView

# The exact gate applied to the view under test.
MARK_EDITING_ROLES = (
    User.Role.ADMIN,
    User.Role.HOD,
    User.Role.TEACHER,
    "HEAD_OF_ACADEMICS",
)


def _fake_has_role(user, role):
    return str(getattr(user, "role", "")).upper() == str(role).upper()


def _stub_user(role):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.is_staff = False
    user.role = role
    return user


class BulkGradeEntryRoleGateSealTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _patches(self):
        return [
            patch("apps.accounts.permissions.has_role", _fake_has_role),
            patch("apps.accounts.portal_roles.has_teacher_hat", return_value=False),
            patch("apps.accounts.portal_roles.has_parent_hat", return_value=False),
        ]

    def _deny_status_on_real_view(self, role):
        request = self.factory.get("/evals/teacher/marks/bulk/")
        request.user = _stub_user(role)
        ctx = self._patches()
        for p in ctx:
            p.start()
        try:
            response = BulkGradeEntryView.as_view()(request)
        finally:
            for p in ctx:
                p.stop()
        return response.status_code

    def test_student_denied_on_real_view(self):
        # user_passes_test redirects denied users (302) before the GET body runs.
        self.assertEqual(self._deny_status_on_real_view(User.Role.STUDENT), 302)

    def test_parent_denied_on_real_view(self):
        self.assertEqual(self._deny_status_on_real_view(User.Role.PARENT), 302)

    def test_gate_admits_mark_editors_and_denies_others(self):
        @role_required(*MARK_EDITING_ROLES)
        def dummy(request):
            return HttpResponse("ok")

        def status(role):
            request = self.factory.get("/x")
            request.user = _stub_user(role)
            ctx = self._patches()
            for p in ctx:
                p.start()
            try:
                return dummy(request).status_code
            finally:
                for p in ctx:
                    p.stop()

        self.assertEqual(status(User.Role.TEACHER), 200)
        self.assertEqual(status(User.Role.ADMIN), 200)
        self.assertEqual(status(User.Role.STUDENT), 302)
        self.assertEqual(status(User.Role.PARENT), 302)
