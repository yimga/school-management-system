"""Owner Console — Support section (Wave 7.4).

The Owner Console front door to the already-unified help center, KB and tickets.
These lock the gate, the render, the nav wiring, that the owner's own tickets +
open count surface, and that another school's tickets never leak in.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsoleSupportTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Support High", subdomain="ocsup-high", slug="ocsup-high", is_active=True,
        )
        self.owner = U.objects.create(username="nora", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN",
            is_school_owner=True, is_primary=True,
        )
        self.member = U.objects.create(username="tim", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role="TEACHER", is_school_owner=False,
        )

    def _req(self, user):
        from django.contrib.sessions.middleware import SessionMiddleware

        req = self.rf.get("/authentication/owner/support/")
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user
        req.school = self.school
        return req

    def _html(self, resp):
        return resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()

    # ── nav wiring ────────────────────────────────────────────────────────────
    def test_nav_includes_support_and_resolves(self):
        from apps.accounts.views_owner_console import _console_sections

        by_key = {s["key"]: s for s in _console_sections("support")}
        self.assertIn("support", by_key)
        self.assertTrue(by_key["support"]["url"])
        self.assertTrue(by_key["support"]["active"])

    # ── gate ──────────────────────────────────────────────────────────────────
    def test_owner_renders_200(self):
        from apps.accounts.views_owner_console_support import owner_console_support

        resp = owner_console_support(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Support", self._html(resp))

    def test_non_owner_forbidden(self):
        from apps.accounts.views_owner_console_support import owner_console_support

        resp = owner_console_support(self._req(self.member))
        self.assertEqual(resp.status_code, 403)

    # ── empty state ───────────────────────────────────────────────────────────
    def test_empty_state_no_500(self):
        from apps.accounts.views_owner_console_support import owner_console_support

        resp = owner_console_support(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("haven", self._html(resp))  # "haven't opened any support tickets yet."

    # ── owner's own tickets + open count ──────────────────────────────────────
    def test_owner_ticket_and_open_count(self):
        from apps.accounts.views_owner_console_support import owner_console_support
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        GlobalSupportTicket.objects.create(
            school=self.school, user=self.owner, subject="Cannot print report cards",
            status=GlobalSupportTicket.Status.OPEN,
        )
        req = self._req(self.owner)
        resp = owner_console_support(req)
        html = self._html(resp)
        self.assertIn("Cannot print report cards", html)
        # assert the open-ticket count directly via the helper
        from apps.accounts.views_owner_console_support import _my_tickets_and_counts

        _tickets, open_count = _my_tickets_and_counts(req)
        self.assertEqual(open_count, 1)

    def test_other_school_tickets_not_leaked(self):
        from apps.accounts.views_owner_console_support import owner_console_support
        from apps.schools.models import School
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        other = School.objects.create(
            name="Other High", subdomain="ocsup-other", slug="ocsup-other", is_active=True,
        )
        other_user = U.objects.create(username="ollie", role="ADMIN")
        GlobalSupportTicket.objects.create(
            school=other, user=other_user, subject="Other-school private ticket",
            status=GlobalSupportTicket.Status.OPEN,
        )
        resp = owner_console_support(self._req(self.owner))
        self.assertNotIn("Other-school private ticket", self._html(resp))

    # ── template compiles ─────────────────────────────────────────────────────
    def test_template_compiles(self):
        from django.template.loader import get_template

        get_template("accounts/owner_console/support.html")
