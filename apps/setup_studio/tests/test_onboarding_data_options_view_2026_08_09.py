"""Seals for the reverse-path onboarding-waiver view (2026-08-09).

The view is how a school that opted into migration and then found it has no data
(or a brand-new school) actually clears the blocker: it waives / un-waives the
migration and roster onboarding decisions, gated to the tenant-admin tier.

These tests FAIL before apps/setup_studio/views_waiver.py exists.
"""
from __future__ import annotations

from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.schools.models import School
from apps.schools import onboarding_waiver as ow
from apps.setup_studio.services import _step_state_for_school
from apps.setup_studio.views_waiver import onboarding_data_options


class OnboardingDataOptionsViewTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Options School",
            slug="options-school",
            subdomain="options-school",
            is_active=True,
            country_code="CM",
        )
        self.admin = User.objects.create_superuser(
            username="opt_admin", email="opt_admin@example.com", password="x"
        )
        self.outsider = User.objects.create_user(username="opt_rando", password="x")

    def _req(self, method, data=None, user=None):
        req = getattr(self.rf, method.lower())(
            "/school/studio/data-options/", data or {}
        )
        req.user = user or self.admin
        req.school = self.school
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _fresh(self):
        return School.objects.get(pk=self.school.pk)

    def test_get_renders_options_for_admin(self):
        captured = {}

        def _fake_render(request, template, context, *a, **k):
            captured["template"] = template
            captured["context"] = context
            return HttpResponse(b"ok")

        with mock.patch(
            "apps.setup_studio.views_waiver.render", _fake_render
        ):
            resp = onboarding_data_options(self._req("get"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            captured["template"], "setup_studio/onboarding_data_options.html"
        )
        self.assertFalse(captured["context"]["migration_waived"])
        self.assertFalse(captured["context"]["roster_waived"])

    def test_post_waive_migration(self):
        resp = onboarding_data_options(
            self._req("post", {"kind": "migration", "action": "waive"})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ow.migration_waived(self._fresh()))

    def test_post_waive_roster_clears_data_path_blocker(self):
        onboarding_data_options(
            self._req("post", {"kind": "roster", "action": "waive"})
        )
        self.assertTrue(_step_state_for_school(self._fresh())["data_path"]["done"])

    def test_post_unwaive_reverts(self):
        ow.waive(self.school, ow.WAIVER_MIGRATION)
        resp = onboarding_data_options(
            self._req("post", {"kind": "migration", "action": "unwaive"})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ow.migration_waived(self._fresh()))

    def test_bad_kind_is_rejected(self):
        resp = onboarding_data_options(
            self._req("post", {"kind": "bogus", "action": "waive"})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ow.get_waiver(self._fresh(), ow.WAIVER_MIGRATION), {})

    def test_non_admin_is_denied(self):
        with self.assertRaises(PermissionDenied):
            onboarding_data_options(
                self._req(
                    "post",
                    {"kind": "migration", "action": "waive"},
                    user=self.outsider,
                )
            )

    def test_template_compiles(self):
        from django.template.loader import get_template

        # Raises TemplateSyntaxError if the page has a tag/argument error.
        get_template("setup_studio/onboarding_data_options.html")
