"""Registry-driven admin outcome deck + changelist crawl gate."""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.siteconfig.admin_model_outcomes import (
    build_admin_outcome_deck_context,
    parse_admin_path,
    resolve_outcome_id,
)
from config.admin import platform_admin_site, tenant_admin_site

User = get_user_model()


class AdminModelOutcomeParserTests(TestCase):
    def test_parse_app_only(self):
        self.assertEqual(parse_admin_path("/admin/siteconfig/"), ("siteconfig", None))

    def test_parse_changelist(self):
        self.assertEqual(
            parse_admin_path("/admin/people/studentprofile/"),
            ("people", "studentprofile"),
        )

    def test_parse_change_form(self):
        self.assertEqual(
            parse_admin_path("/admin/people/studentprofile/12/change/"),
            ("people", "studentprofile"),
        )

    def test_resolve_default(self):
        self.assertEqual(resolve_outcome_id("unknown_app_xyz", None), "runtime_policies")

    def test_resolve_finance(self):
        self.assertEqual(resolve_outcome_id("finance", None), "billing_commercial")


class AdminOutcomeDeckContextTests(TestCase):
    def test_deck_none_for_non_admin_path(self):
        rf = RequestFactory().get("/portal/")
        rf.public_host_kind = "manager"
        self.assertIsNone(
            build_admin_outcome_deck_context(rf, is_platform_site=True),
        )

    def test_deck_for_model_path_has_title_and_links(self):
        rf = RequestFactory().get("/admin/policies/countryprofile/")
        rf.public_host_kind = "manager"
        rf.user = User.objects.create_superuser("t1", "t1@t.com", "x")
        deck = build_admin_outcome_deck_context(rf, is_platform_site=True)
        self.assertIsNotNone(deck)
        assert deck is not None
        self.assertEqual(deck["admin_deck_app_label"], "policies")
        self.assertEqual(deck["admin_deck_model_name"], "countryprofile")
        self.assertTrue(deck["admin_deck_title"])


@override_settings(ALLOWED_HOSTS=["*", "testserver", "localhost", ".runmycampus.com"])
class PlatformAdminChangelistCrawlTests(TestCase):
    """Authenticated crawl of every platform admin changelist — blocks dead admin routes."""

    def setUp(self):
        self.user = User.objects.create_superuser("crawl", "crawl@t.com", "pw")
        self.client = Client()
        self.client.force_login(self.user)

    def test_all_platform_changelists_reachable(self):
        allow = {200, 302, 301}
        skipped = 0
        bad: list[tuple[str, int]] = []
        for model in platform_admin_site._registry:
            opts = model._meta
            name = f"admin:{opts.app_label}_{opts.model_name}_changelist"
            try:
                url = reverse(name)
            except Exception:
                skipped += 1
                continue
            r = self.client.get(url)
            if r.status_code not in allow:
                bad.append((url, r.status_code))
        self.assertEqual(
            bad,
            [],
            msg=f"Changelist failures (url, status): {bad[:20]}; skipped={skipped}",
        )


@override_settings(ALLOWED_HOSTS=["*"])
@patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
class TenantAdminChangelistCrawlTests(TestCase):
    """
    Full tenant admin registry on a real tenant host (urlconf tenant_urls).
    Superuser required (TenantAdminSite policy).
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Tenant Crawl School",
            slug="tenant-crawl",
            subdomain="tenant-crawl",
            is_active=True,
        )
        self.host = "tenant-crawl.example.com"
        self.user = User.objects.create_superuser("tcrawl", "tcrawl@t.com", "pw")
        self.client = Client(HTTP_HOST=self.host)
        self.client.force_login(self.user)

    def test_all_tenant_changelists_reachable(self):
        allow = {200, 302, 301}
        skipped = 0
        bad: list[tuple[str, int]] = []
        for model in tenant_admin_site._registry:
            opts = model._meta
            name = f"admin:{opts.app_label}_{opts.model_name}_changelist"
            try:
                url = reverse(name, urlconf="config.tenant_urls")
            except Exception:
                skipped += 1
                continue
            r = self.client.get(url)
            if r.status_code not in allow:
                bad.append((url, r.status_code))
        self.assertEqual(
            bad,
            [],
            msg=f"Tenant changelist failures: {bad[:25]}; skipped={skipped}",
        )
