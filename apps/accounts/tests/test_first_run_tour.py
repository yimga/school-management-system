"""T17: per-role first-run guided tour — autostart gate + per-context completion.

The tour ENGINE (rmc-tour.js), steps API, and catalog already existed and were
wired for the admin dashboard only. T17 lights up the teacher / parent / student
role landings by:
  * a ``first_run_tour`` context processor that resolves the tour context on the
    three role landings and reports whether THIS user has finished that role's
    tour (so ``portal_base`` autostarts it exactly once), and
  * generalizing ``mark_tour_complete`` to remember completion PER role context
    (backward compatible with the admin ``backend_dashboard`` key).

These tests lock both halves.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.dashboard.context_processors import first_run_tour

U = get_user_model()


def _user(username):
    u = U.objects.create(username=username)
    u.set_password("x")
    u.save()
    return u


class FirstRunTourContextProcessorTests(TestCase):
    def _req(self, view_name, user):
        r = RequestFactory().get("/portal/teacher/")
        r.user = user
        r.resolver_match = SimpleNamespace(view_name=view_name)
        return r

    def test_anonymous_returns_empty(self):
        r = self._req("portal:teacher_dashboard_alias", AnonymousUser())
        self.assertEqual(first_run_tour(r), {})

    def test_non_landing_returns_empty(self):
        r = self._req("portal:some_other_page", _user("frt-nonland"))
        self.assertEqual(first_run_tour(r), {})

    def test_no_resolver_match_returns_empty(self):
        r = RequestFactory().get("/whatever/")
        r.user = _user("frt-noresolve")
        # no resolver_match set at all
        self.assertEqual(first_run_tour(r), {})

    def test_teacher_landing_fresh_user_autostarts(self):
        ctx = first_run_tour(self._req("portal:teacher_dashboard_alias", _user("frt-teacher")))
        self.assertEqual(ctx["rmc_fr_tour_context"], "teacher_portal")
        self.assertTrue(ctx["rmc_fr_tour_show"])
        self.assertIn("context=teacher_portal", ctx["rmc_fr_tour_complete_url"])

    def test_parent_and_student_contexts_resolve(self):
        u = _user("frt-multi")
        self.assertEqual(
            first_run_tour(self._req("portal:parent_dashboard", u))["rmc_fr_tour_context"],
            "parent_portal",
        )
        self.assertEqual(
            first_run_tour(self._req("portal:student_portal_grades", u))["rmc_fr_tour_context"],
            "student_portal",
        )

    def test_completed_user_does_not_autostart(self):
        u = _user("frt-done")
        from apps.runtime_blueprints.models import DashboardUserPreference

        # A DashboardUserPreference may already exist (created by a User signal),
        # so update_or_create rather than create.
        DashboardUserPreference.objects.update_or_create(
            user=u, defaults={"dashboard_layout": {"tour_teacher_portal_completed": True}}
        )
        ctx = first_run_tour(self._req("portal:teacher_dashboard_alias", u))
        self.assertFalse(ctx["rmc_fr_tour_show"])

    def test_completion_is_per_role(self):
        """Finishing the teacher tour must NOT suppress the parent tour."""
        u = _user("frt-perrole")
        from apps.runtime_blueprints.models import DashboardUserPreference

        DashboardUserPreference.objects.update_or_create(
            user=u, defaults={"dashboard_layout": {"tour_teacher_portal_completed": True}}
        )
        parent_ctx = first_run_tour(self._req("portal:parent_dashboard", u))
        self.assertTrue(parent_ctx["rmc_fr_tour_show"])


class MarkTourCompletePerContextTests(TestCase):
    def _login(self, username):
        u = _user(username)
        self.client.force_login(u)
        return u

    def _layout(self, user):
        from apps.runtime_blueprints.models import DashboardUserPreference

        return DashboardUserPreference.objects.get(user=user).dashboard_layout

    def test_context_stores_per_context_key(self):
        u = self._login("mtc-teacher")
        resp = self.client.post(
            reverse("accounts:mark_tour_complete") + "?context=teacher_portal"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._layout(u).get("tour_teacher_portal_completed"))

    def test_no_context_is_backward_compatible(self):
        u = self._login("mtc-admin")
        resp = self.client.post(reverse("accounts:mark_tour_complete"))
        self.assertEqual(resp.status_code, 200)
        # Admin's completeUrl carries no context → the original key is written.
        self.assertTrue(self._layout(u).get("tour_backend_dashboard_completed"))

    def test_malicious_context_is_rejected(self):
        u = self._login("mtc-evil")
        resp = self.client.post(
            reverse("accounts:mark_tour_complete") + "?context=../../evil%20key"
        )
        self.assertEqual(resp.status_code, 200)
        layout = self._layout(u)
        # Falls back to the safe default; never writes an attacker-controlled key.
        self.assertTrue(layout.get("tour_backend_dashboard_completed"))
        self.assertEqual(
            [k for k in layout if k.startswith("tour_") and "evil" in k], []
        )
