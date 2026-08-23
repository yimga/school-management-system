"""
The operator school-invite accept link must resolve on the host the email targets.

``send_tenant_invite_email`` builds ``{RMC_PUBLIC_SITE_URL}/accept-invite/?token=..``
(defaulting to https://runmycampus.com). ``UrlConfSwitcherMiddleware`` classifies
that host as ``base`` and routes it to ``config.public_urls`` -- where the route
does not exist. It is registered ONLY in ``config/urls.py``, which is served for
``testserver``/localhost, which is exactly why the existing invite tests
(test_invite_school.py, test_invite_provision_e2e.py) stay green while every real
invitation email 404s.

These assert against the URLCONF MODULE rather than going through the test client,
so the host split cannot hide the gap again.
"""

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

from apps.schools.host_routing import public_host_kind
from apps.schools.super_views_invite_school import _public_base_url


class AcceptInviteRoutedOnPublicHostTests(SimpleTestCase):
    def test_invite_email_targets_a_base_domain_host(self):
        """Guard the premise: the emailed link points at a `base`-kind host."""
        host = _public_base_url().split("://", 1)[-1].split("/", 1)[0]
        self.assertEqual(
            public_host_kind(host),
            "base",
            f"invite link host {host!r} is no longer a base host; "
            "re-check which urlconf serves it",
        )

    def test_accept_invite_resolves_on_public_urls(self):
        """The urlconf a base host is actually served must carry the route."""
        try:
            match = resolve("/accept-invite/", urlconf="config.public_urls")
        except Resolver404:
            self.fail(
                "/accept-invite/ does not resolve in config.public_urls -- every "
                "operator school-invite email 404s. Fix: add "
                '    path("accept-invite/", accept_school_invite, '
                'name="accept_school_invite"), '
                "to config/public_urls.py (import accept_school_invite from "
                "apps.schools.signup_views), prepending it like the Wave 25 LTI "
                "block so the 2-segment regional catch-all cannot swallow it."
            )
        self.assertEqual(match.url_name, "accept_school_invite")

    def test_accept_invite_still_resolves_on_dev_urlconf(self):
        """config.urls keeps the route for local/dev hosts."""
        match = resolve("/accept-invite/", urlconf=settings.ROOT_URLCONF)
        self.assertEqual(match.url_name, "accept_school_invite")
