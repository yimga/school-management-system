"""Registry-driven admin outcome deck + changelist crawl gate."""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.test_utils.tenant_hosts import BASE_DOMAIN, MANAGER_HOST, host_routed
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

    def test_tenant_deck_filters_operator_and_studio_links(self):
        rf = RequestFactory().get(
            "/admin/brand_experience/themepack/",
            HTTP_HOST="demo-school.runmycampus.com",
        )
        rf.public_host_kind = "tenant"
        rf.urlconf = "config.tenant_urls"
        rf.user = User.objects.create_superuser("tenant-deck", "tenant-deck@t.com", "x")

        deck = build_admin_outcome_deck_context(rf, is_platform_site=False)

        self.assertIsNotNone(deck)
        assert deck is not None
        links = list(deck["admin_deck_links"]) + list(
            deck["admin_deck_tenant_shortcuts"]
        )
        rendered = " ".join(
            f"{link.get('label', '')} {link.get('url', '')}" for link in links
        ).lower()
        self.assertNotIn("studio", rendered)
        self.assertNotIn("/super/", rendered)
        self.assertNotIn("fleet", rendered)


class _ChangelistCrawlMixin:
    """Render every registered changelist and require a real page back.

    The previous version of this crawl could pass having rendered nothing, in
    two independent ways, and on the platform site it did:

    * ``reverse(name)`` with no urlconf resolves against ``ROOT_URLCONF``
      (``config.urls``), where the PLATFORM admin is not mounted -- it lives on
      ``config.manager_urls``, behind the manager host. All 223 models raised
      ``NoReverseMatch``, every one was swallowed by ``except Exception:
      skipped += 1``, and the assertion compared an empty list to an empty list.
      **Zero requests were made**, by a test whose docstring says it "blocks dead
      admin routes". ``skipped`` was only printed inside the failure message, so
      the number that would have given it away was never shown.
    * ``allow = {200, 302, 301}`` accepts a redirect, and ``force_login`` does
      not satisfy MFA. On the manager host every changelist 302s to
      ``/authentication/mfa/setup/`` -- so even after fixing the urlconf, the
      crawl would have gone green against 223 redirects to a login wall.

    Both are fixed here: the request goes to the host that really serves the
    site, MFA is satisfied so pages render, a skip is a FAILURE rather than a
    silent pass, and only a 200 counts. Measured after the fix: 222/223 platform
    and 287/288 tenant changelists return 200, the remainder being the
    security-posture nag, which is disabled under the test runner.
    """

    #: A refusal that is a deliberate product gate rather than a broken page.
    #: Kept exact so a NEW redirect cannot hide behind it.
    ALLOWED_REDIRECT_FRAGMENT = "/authentication/profile/security/review/"

    def _mfa_client(self, user, host):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.update_or_create(
            user=user, name="changelist-crawl", defaults={"confirmed": True}
        )
        client = Client(HTTP_HOST=host)
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def _crawl(self, site, client, urlconf):
        bad, skipped = [], []
        for model in site._registry:
            opts = model._meta
            name = f"admin:{opts.app_label}_{opts.model_name}_changelist"
            try:
                url = reverse(name, urlconf=urlconf)
            except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
                skipped.append(f"{name} ({type(exc).__name__})")
                continue
            resp = client.get(url)
            if resp.status_code == 200:
                continue
            location = resp.headers.get("Location") or ""
            if (
                resp.status_code in (301, 302)
                and self.ALLOWED_REDIRECT_FRAGMENT in location
            ):
                continue
            bad.append((url, resp.status_code, location[:60]))

        self.assertEqual(
            skipped,
            [],
            "changelists that would not reverse -- the crawl cannot see these, "
            f"so it is not crawling the whole site: {skipped[:15]}",
        )
        self.assertEqual(
            bad,
            [],
            f"changelists that did not render (url, status, location): {bad[:20]}",
        )
        self.assertGreater(
            len(site._registry),
            50,
            "the registry looks empty -- a crawl over nothing proves nothing",
        )


@host_routed
class PlatformAdminChangelistCrawlTests(_ChangelistCrawlMixin, TestCase):
    """Every platform admin changelist, on the host that actually serves it."""

    def test_all_platform_changelists_render(self):
        user = User.objects.create_superuser("crawl_p", "crawl_p@t.com", "pw")
        client = self._mfa_client(user, MANAGER_HOST)
        self._crawl(platform_admin_site, client, "config.manager_urls")


@host_routed
class TenantAdminChangelistCrawlTests(_ChangelistCrawlMixin, TestCase):
    """Every tenant admin changelist, on a real tenant host."""

    def setUp(self):
        self.school = School.objects.create(
            name="Tenant Crawl School",
            slug="tenant-crawl",
            subdomain="tenant-crawl",
            is_active=True,
        )

    def test_all_tenant_changelists_render(self):
        user = User.objects.create_superuser("crawl_t", "crawl_t@t.com", "pw")
        client = self._mfa_client(user, f"{self.school.subdomain}.{BASE_DOMAIN}")
        self._crawl(tenant_admin_site, client, "config.tenant_urls")
