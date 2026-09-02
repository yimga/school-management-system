"""The Workflow Center must not advertise a destination the viewer cannot open.

Sweeping all 44 destinations as a REAL tenant admin (not a superuser — superusers
short-circuit every gate, which is exactly why the problem stayed invisible) showed
four rows that the admin-gated Workflow Center offers but an admin cannot use:

  * ``evals:teacher_marks_entry`` / ``evals:teacher_marks_list`` — ``@role_required(TEACHER)``
    is a ``user_passes_test``, so an admin is REDIRECTED TO LOGIN while already signed in.
    That reads as a broken session, which is worse than a plain refusal.
  * ``evals:grade_approval_list`` — a second in-view gate (``_user_can_review_grades``)
    resolves the approver role set from per-school policy, so holding ``grades.manage``
    is not sufficient; the miss returns a bare unstyled ``HttpResponseForbidden``.
  * ``portal:portal_feature`` (Public documents) — gated on ``documents.view``, which the
    ADMIN role does not carry by default.

Link RESOLUTION is sealed separately (test_workflow_center_link_integrity). This module
seals link REACHABILITY: the row is dropped for a viewer who would be bounced, and the
step renders an honest note rather than a blank card.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.models import User
from apps.accounts.views_workflow import (
    _LINK_VISIBILITY,
    _viewer_is_teacher,
)
from apps.siteconfig.tests._template_nodes import assert_markup


class _FakeUser:
    def __init__(self, role="", is_superuser=False, authenticated=True, perms=()):
        self.role = role
        self.is_superuser = is_superuser
        self.is_authenticated = authenticated
        self._perms = set(perms)

    def has_feature_permission(self, code, school=None):
        return code in self._perms


class _FakeRequest:
    def __init__(self, user, school=None):
        self.user = user
        self.school = school


class VisibilityRegistryShapeTests(SimpleTestCase):
    """The registry is the contract; keep it honest and keyed on real URL names."""

    def test_registry_covers_the_confirmed_unreachable_rows(self):
        for name in (
            "evals:teacher_marks_entry",
            "evals:teacher_marks_list",
            "evals:grade_approval_list",
            "portal:portal_feature",
        ):
            self.assertIn(name, _LINK_VISIBILITY)

    def test_every_predicate_is_callable(self):
        for name, predicate in _LINK_VISIBILITY.items():
            with self.subTest(name=name):
                self.assertTrue(callable(predicate))


class TeacherOnlyRowsTests(SimpleTestCase):
    """The marks surfaces are teacher-gated; an admin must not be offered them."""

    def test_admin_is_not_a_teacher(self):
        req = _FakeRequest(_FakeUser(role=User.Role.ADMIN))
        self.assertFalse(_viewer_is_teacher(req))

    def test_teacher_is_a_teacher(self):
        req = _FakeRequest(_FakeUser(role=User.Role.TEACHER))
        self.assertTrue(_viewer_is_teacher(req))

    def test_superuser_keeps_every_row(self):
        req = _FakeRequest(_FakeUser(role=User.Role.ADMIN, is_superuser=True))
        self.assertTrue(_viewer_is_teacher(req))

    def test_anonymous_is_not_a_teacher(self):
        req = _FakeRequest(_FakeUser(role="", authenticated=False))
        self.assertFalse(_viewer_is_teacher(req))


class PermissionBackedRowsTests(SimpleTestCase):
    """`Public documents` is gated on documents.view."""

    def setUp(self):
        self.predicate = _LINK_VISIBILITY["portal:portal_feature"]

    def test_admin_without_documents_view_is_filtered_out(self):
        req = _FakeRequest(_FakeUser(role=User.Role.ADMIN, perms=()))
        self.assertFalse(self.predicate(req))

    def test_holder_of_documents_view_keeps_the_row(self):
        req = _FakeRequest(_FakeUser(role=User.Role.ADMIN, perms=("documents.view",)))
        self.assertTrue(self.predicate(req))

    def test_superuser_keeps_the_row(self):
        req = _FakeRequest(_FakeUser(role=User.Role.ADMIN, is_superuser=True))
        self.assertTrue(self.predicate(req))


class FilterFailsOpenTests(SimpleTestCase):
    """An unknown answer must keep the row, never silently delete a real surface."""

    def test_permission_lookup_error_keeps_the_row(self):
        class Exploding:
            is_authenticated = True
            is_superuser = False
            role = User.Role.ADMIN

            def has_feature_permission(self, code, school=None):
                raise ValueError("permission backend unavailable")

        predicate = _LINK_VISIBILITY["portal:portal_feature"]
        self.assertTrue(predicate(_FakeRequest(Exploding())))


class EmptyStepRendersAnExplanationTests(SimpleTestCase):
    """Filtering can empty a step — a blank card reads as a broken page."""

    def test_step_link_loop_has_an_empty_branch(self):
        workflow_main = (
            Path(settings.BASE_DIR)
            / "templates"
            / "accounts"
            / "partials"
            / "workflow_center_main.html"
        )
        markup = workflow_main.read_text(encoding="utf8")
        # {% empty %} is a tag and the note is a {% trans %} msgid: both are
        # template code, so both stay source reads.
        self.assertIn("{% empty %}", markup)
        self.assertIn("Nothing here for your role", markup)
        # The branch only helps if it renders. Its <p> is the one element in the
        # file carrying this class list, and a class list IS emitted text -- so
        # this asserts the honest note exists as markup, not merely as bytes.
        assert_markup(self, workflow_main, "workflow-subtitle wrap mb-0 text-muted")


class LinksCarryTheirUrlNameTests(SimpleTestCase):
    """The filter keys on url_name, so _workflow_link must emit it."""

    def test_workflow_link_includes_url_name(self):
        from apps.accounts.views_workflow import _workflow_link

        with self.settings(ROOT_URLCONF="config.tenant_urls"):
            link = _workflow_link("Clone previous year", "accounts:clone_year_setup")
        self.assertIsNotNone(link)
        self.assertEqual(link["url_name"], "accounts:clone_year_setup")
        self.assertTrue(link["url"])
