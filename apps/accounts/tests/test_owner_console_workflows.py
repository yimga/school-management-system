"""Owner Console — Workflows registry (Wave 7.1).

A read-only, owner-gated overview of the school's own automations. These lock the
gate, the render, the nav wiring, and — critically — that a real workflow row shows
up while the page stays fail-soft when there are none.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsoleWorkflowsTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Workflow High", subdomain="ocw-high", slug="ocw-high", is_active=True,
        )
        self.owner = U.objects.create(username="nadia", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN",
            is_school_owner=True, is_primary=True,
        )
        self.member = U.objects.create(username="theo", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role="TEACHER", is_school_owner=False,
        )

    def _req(self, user):
        from django.contrib.sessions.middleware import SessionMiddleware

        req = self.rf.get("/authentication/owner/workflows/")
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user
        req.school = self.school
        return req

    def _html(self, resp):
        return resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()

    # ── nav wiring ────────────────────────────────────────────────────────────
    def test_nav_includes_workflows_and_resolves(self):
        from apps.accounts.views_owner_console import _console_sections

        sections = _console_sections("workflows")
        by_key = {s["key"]: s for s in sections}
        self.assertIn("workflows", by_key)
        self.assertTrue(by_key["workflows"]["url"])  # route resolves
        self.assertTrue(by_key["workflows"]["active"])

    # ── gate ──────────────────────────────────────────────────────────────────
    def test_owner_renders_200(self):
        from apps.accounts.views_owner_console_workflows import owner_console_workflows

        resp = owner_console_workflows(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Workflows", self._html(resp))

    def test_non_owner_forbidden(self):
        from apps.accounts.views_owner_console_workflows import owner_console_workflows

        resp = owner_console_workflows(self._req(self.member))
        self.assertEqual(resp.status_code, 403)

    # ── empty state is fail-soft ──────────────────────────────────────────────
    def test_empty_state_no_500(self):
        from apps.accounts.views_owner_console_workflows import owner_console_workflows

        resp = owner_console_workflows(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Nothing here yet.", self._html(resp))

    # ── a real automation surfaces ────────────────────────────────────────────
    def test_school_automation_row_surfaces(self):
        from apps.accounts.views_owner_console_workflows import owner_console_workflows
        from apps.siteconfig.models_workflow import SchoolAutomationWorkflow

        SchoolAutomationWorkflow.objects.create(
            school=self.school, name="Welcome new student", trigger="student_created",
            status=SchoolAutomationWorkflow.Status.PUBLISHED, is_active=True,
        )
        resp = owner_console_workflows(self._req(self.owner))
        html = self._html(resp)
        self.assertIn("Welcome new student", html)
        self.assertIn("student_created", html)

    def test_only_own_school_workflows_listed(self):
        from apps.accounts.views_owner_console_workflows import owner_console_workflows
        from apps.schools.models import School
        from apps.siteconfig.models_workflow import SchoolAutomationWorkflow

        other = School.objects.create(
            name="Other High", subdomain="ocw-other", slug="ocw-other", is_active=True,
        )
        SchoolAutomationWorkflow.objects.create(
            school=other, name="Other-school secret flow", trigger="payment_received",
            status=SchoolAutomationWorkflow.Status.PUBLISHED, is_active=True,
        )
        resp = owner_console_workflows(self._req(self.owner))
        self.assertNotIn("Other-school secret flow", self._html(resp))

    # ── template compiles ─────────────────────────────────────────────────────
    def test_template_compiles(self):
        from django.template.loader import get_template

        get_template("accounts/owner_console/workflows.html")
