"""Currency editor — a real tenant override the config resolver actually reads.

The Portal-Configure "Currency & taxes" tile used to land on a generic runtime
hub; it now opens this editor. The editor writes ``school.settings['default_currency']``,
the exact key ``siteconfig.tenant_config`` maps to ``out['currency']`` — so a
saved value is a live override, not a display-only screen. These lock that:
a valid code persists to the consumed key, an unknown code is rejected, and a
non-admin is refused.
"""
from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponseForbidden
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig.views import currency_settings


def _req(method, school, user, data=None):
    req = getattr(RequestFactory(), method)("/siteconfig/currency-settings/", data or {})
    req.school = school
    req.user = user
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    return req


class CurrencySettingsEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Currency School",
            slug="currency-school",
            subdomain="currency-school",
            is_active=True,
        )
        cls.admin = User.objects.create_superuser(
            username="currency_admin", email="c@d.co", password="x"
        )

    def test_valid_code_persists_to_the_consumed_key(self):
        resp = currency_settings(
            _req("post", self.school, self.admin, {"default_currency": "NGN"})
        )
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertEqual(self.school.settings.get("default_currency"), "NGN")
        # Prove the write is actually the key the tenant config resolver reads —
        # and that the region overlay (guarded on empty/USD) does not clobber it.
        from apps.siteconfig.tenant_config import get_tenant_locale

        cfg = get_tenant_locale(school=self.school)
        self.assertEqual(cfg.get("currency"), "NGN")

    def test_unknown_code_is_rejected_and_not_persisted(self):
        resp = currency_settings(
            _req("post", self.school, self.admin, {"default_currency": "ZZZ"})
        )
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertNotEqual((self.school.settings or {}).get("default_currency"), "ZZZ")

    def test_get_renders_for_admin(self):
        resp = currency_settings(_req("get", self.school, self.admin))
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_is_forbidden(self):
        nobody = User.objects.create_user(
            username="currency_nobody", password="x", role=User.Role.STUDENT
        )
        resp = currency_settings(
            _req("post", self.school, nobody, {"default_currency": "NGN"})
        )
        self.assertIsInstance(resp, HttpResponseForbidden)
        self.school.refresh_from_db()
        self.assertNotEqual((self.school.settings or {}).get("default_currency"), "NGN")
