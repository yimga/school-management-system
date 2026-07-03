"""Owner Console — Context Profile wizard (Wave 7.2).

Locks the gate, the nav wiring, the stepped render, and — the point of the whole
slice — that each step writes a real first-class config value through the resolver
(``set_runtime_default`` → readable by ``get_effective_config``) with no migration.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsoleContextProfileTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Context High", subdomain="occp-high", slug="occp-high", is_active=True,
        )
        self.owner = U.objects.create(username="nia", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN",
            is_school_owner=True, is_primary=True,
        )
        self.member = U.objects.create(username="tom", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role="TEACHER", is_school_owner=False,
        )

    def _req(self, user, method="get", data=None, step=None):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        path = "/authentication/owner/setup/"
        if method == "get" and step is not None:
            path += f"?step={step}"
        req = getattr(self.rf, method)(path, data or {})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req._messages = FallbackStorage(req)
        req.user = user
        req.school = self.school
        return req

    def _view(self):
        from apps.accounts.views_owner_console_context_profile import owner_console_context_profile

        return owner_console_context_profile

    def _html(self, resp):
        return resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()

    # ── nav wiring ────────────────────────────────────────────────────────────
    def test_nav_includes_setup_and_resolves(self):
        from apps.accounts.views_owner_console import _console_sections

        by_key = {s["key"]: s for s in _console_sections("setup")}
        self.assertIn("setup", by_key)
        self.assertTrue(by_key["setup"]["url"])
        self.assertTrue(by_key["setup"]["active"])

    # ── gate ──────────────────────────────────────────────────────────────────
    def test_owner_renders_step1(self):
        resp = self._view()(self._req(self.owner, step=1))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Where is your school?", self._html(resp))

    def test_non_owner_forbidden(self):
        resp = self._view()(self._req(self.member, step=1))
        self.assertEqual(resp.status_code, 403)

    # ── step 1 writes region into the config cascade ──────────────────────────
    def test_step1_writes_country_region_to_resolver(self):
        from apps.platform_runtime.config_resolver import get_effective_config

        resp = self._view()(self._req(self.owner, "post", {"step": "1", "country": "ng", "region": "Lagos"}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("step=2", resp["Location"])
        self.school.refresh_from_db()
        self.assertEqual(get_effective_config(self.school, "country"), "NG")  # upper-cased
        self.assertEqual(get_effective_config(self.school, "region"), "Lagos")

    # ── step 2 writes a valid grading scale, ignores an invalid one ───────────
    def test_step2_writes_valid_grading_scale(self):
        from apps.platform_runtime.config_resolver import get_effective_config

        resp = self._view()(self._req(self.owner, "post", {"step": "2", "grading_scale": "LETTER"}))
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertEqual(get_effective_config(self.school, "default_grading_scale"), "LETTER")

    def test_step2_ignores_unknown_grading_scale(self):
        from apps.platform_runtime.config_resolver import get_effective_config

        self._view()(self._req(self.owner, "post", {"step": "2", "grading_scale": "NOT_A_SCALE"}))
        self.school.refresh_from_db()
        self.assertNotEqual(get_effective_config(self.school, "default_grading_scale"), "NOT_A_SCALE")

    # ── step 3 completes the profile ──────────────────────────────────────────
    def test_step3_marks_complete(self):
        resp = self._view()(self._req(self.owner, "post", {"step": "3"}))
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        state = (self.school.settings or {}).get("context_profile", {})
        self.assertTrue(state.get("completed"))

    # ── template compiles ─────────────────────────────────────────────────────
    def test_template_compiles(self):
        from django.template.loader import get_template

        get_template("accounts/owner_console/context_profile.html")
