"""Owner Console — slice 4: section sub-pages.

Modules / Billing / Data / Branding / Audit each render inside the console shell,
are owner-gated + fail-soft, and deep-link ("Open full …") into the existing hub.
The Audit section additionally surfaces the school's recent SecurityAuditLog events.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()

SECTIONS = ("modules", "billing", "data", "branding", "audit")


class OwnerConsoleSectionsTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High School", subdomain="ocs-newhigh", slug="ocs-newhigh", is_active=True,
        )
        self.owner = U.objects.create(username="nina", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN", is_school_owner=True, is_primary=True,
        )
        self.member = U.objects.create(username="sam", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role="TEACHER", is_school_owner=False,
        )

    def _req(self, user, section):
        from django.contrib.sessions.middleware import SessionMiddleware

        req = self.rf.get(f"/authentication/owner/{section}/")
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user
        req.school = self.school
        return req

    def _view(self, section):
        from apps.accounts import views_owner_console as v

        return getattr(v, f"owner_console_{section}")

    # ── nav ──────────────────────────────────────────────────────────────────
    def test_sections_include_data_and_all_resolve(self):
        from apps.accounts.views_owner_console import _console_sections

        sections = _console_sections("modules")
        keys = {s["key"] for s in sections}
        for key in ("overview", "people", "modules", "billing", "data", "branding", "audit"):
            self.assertIn(key, keys)
        # every returned section has a resolvable url + exactly one active
        self.assertTrue(all(s["url"] for s in sections))
        self.assertEqual(sum(1 for s in sections if s["active"]), 1)
        self.assertTrue(next(s for s in sections if s["key"] == "modules")["active"])

    # ── gate + render ────────────────────────────────────────────────────────
    def test_every_section_owner_renders(self):
        for section in SECTIONS:
            resp = self._view(section)(self._req(self.owner, section))
            self.assertEqual(resp.status_code, 200, section)
            html = resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()
            self.assertIn("Owner Console", html)

    def test_every_section_non_owner_forbidden(self):
        for section in SECTIONS:
            resp = self._view(section)(self._req(self.member, section))
            self.assertEqual(resp.status_code, 403, section)

    # ── audit surfaces real events ───────────────────────────────────────────
    def test_audit_surfaces_recent_event(self):
        from apps.accounts.models import SecurityAuditLog
        from apps.accounts.views_owner_console import owner_console_audit

        SecurityAuditLog.objects.create(
            school=self.school, user=self.owner, event_type="OWNERSHIP_CHANGED",
        )
        resp = owner_console_audit(self._req(self.owner, "audit"))
        html = resp.content.decode()
        self.assertIn("School ownership changed", html)

    def test_audit_empty_state_no_500(self):
        from apps.accounts.views_owner_console import owner_console_audit

        resp = owner_console_audit(self._req(self.owner, "audit"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("No security events recorded yet.", html)

    # ── templates compile ────────────────────────────────────────────────────
    def test_templates_compile(self):
        from django.template.loader import get_template

        for section in SECTIONS:
            get_template(f"accounts/owner_console/{section}.html")
