"""Platform legal/marketing pages must not 500 on a tenant subdomain.

``marketing_page`` renders the PUBLIC marketing shell, which reverses
public-host-only URL names (``find_school`` / ``global_login_discovery`` /
``tour_steps_public_api`` …). On a tenant subdomain those names aren't
registered, so the shell render is a NoReverseMatch 500. These pages are not
tenant-scoped, so on a tenant host the view now redirects to the canonical
public-host copy. This fires against the pre-fix code (which 500'd).
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings as django_settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.schools.marketing_views import marketing_page
from apps.schools.models import School


def _fresh_session():
    return import_module(django_settings.SESSION_ENGINE).SessionStore()


class MarketingPageTenantRedirectTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory(HTTP_HOST="oak.runmycampus.com")
        self.school = School.objects.create(
            name="Oak", slug="oak-mp", subdomain="oak-mp", is_active=True
        )

    def _request(self, path):
        request = self.factory.get(path)
        request.session = _fresh_session()
        request.user = AnonymousUser()
        return request

    def test_tenant_host_redirects_to_public_copy(self):
        request = self._request("/privacy/")
        request.school = self.school  # tenant context (set by tenant middleware)
        resp = marketing_page(request, "privacy")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/privacy/", resp["Location"])
        # Redirect target is the public marketing host, not the tenant subdomain.
        self.assertNotIn("oak-mp", resp["Location"])

    def test_public_host_still_renders(self):
        # No request.school → public/root host → the page renders as before.
        request = self._request("/privacy/")
        request.school = None
        resp = marketing_page(request, "privacy")
        self.assertEqual(resp.status_code, 200)
