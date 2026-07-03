"""Owner Console — slice 2: tenant-skinned console shell + Overview.

The console is owner-gated (only an actual owner or a platform superuser may open
it), tenant-skinned, and fail-soft. It surfaces the school's people/owners/plan and
deep-links into the existing Tenant Identity hub.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsoleTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High School",
            subdomain="oc-newhigh",
            slug="oc-newhigh",
            is_active=True,
        )
        self.owner = U.objects.create(username="nina", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN",
            is_school_owner=True, is_primary=True,
        )
        self.member = U.objects.create(username="sam", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role="TEACHER", is_school_owner=False,
        )

    def _req(self, user, method="get"):
        from django.contrib.sessions.middleware import SessionMiddleware

        req = getattr(self.rf, method)("/authentication/owner/")
        # portal_base's context processors read request.session; RequestFactory
        # doesn't attach one, so wire a real session store (as middleware would).
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user
        req.school = self.school
        return req

    # ── gate ─────────────────────────────────────────────────────────────────
    def test_gate_owner_true_member_false(self):
        from apps.accounts.views_owner_console import is_school_owner

        self.assertTrue(is_school_owner(self.owner, self.school))
        self.assertFalse(is_school_owner(self.member, self.school))
        self.assertFalse(is_school_owner(AnonymousUser(), self.school))

    def test_gate_superuser_true(self):
        from apps.accounts.views_owner_console import is_school_owner

        su = U.objects.create(username="root", is_superuser=True, is_staff=True)
        self.assertTrue(is_school_owner(su, self.school))

    # ── helpers ──────────────────────────────────────────────────────────────
    def test_sections_include_overview_and_drop_dead_links(self):
        from apps.accounts.views_owner_console import _console_sections

        sections = _console_sections("overview")
        keys = {s["key"] for s in sections}
        self.assertIn("overview", keys)
        self.assertIn("people", keys)  # tenant_identity_roster resolves
        # every returned section has a resolvable url + exactly one active
        self.assertTrue(all(s["url"] for s in sections))
        self.assertEqual(sum(1 for s in sections if s["active"]), 1)

    def test_metrics_count_people_and_owners(self):
        from apps.accounts.views_owner_console import _overview_metrics

        m = _overview_metrics(self.school)
        self.assertEqual(m["people_count"], 2)
        self.assertEqual(m["owner_count"], 1)
        self.assertEqual(len(m["owner_rows"]), 1)
        self.assertTrue(m["plan_label"])

    # ── view ─────────────────────────────────────────────────────────────────
    def test_non_owner_forbidden(self):
        from apps.accounts.views_owner_console import owner_console_overview

        resp = owner_console_overview(self._req(self.member))
        self.assertEqual(resp.status_code, 403)

    def test_owner_renders_overview(self):
        from apps.accounts.views_owner_console import owner_console_overview

        resp = owner_console_overview(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        html = resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()
        self.assertIn("Owner Console", html)

    def test_template_compiles(self):
        from django.template.loader import get_template

        get_template("accounts/owner_console/overview.html")
