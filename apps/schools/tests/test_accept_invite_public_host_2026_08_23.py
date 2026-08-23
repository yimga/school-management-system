"""
The operator school-invite link must resolve on the host the email points at.

``send_tenant_invite_email`` builds ``{RMC_PUBLIC_SITE_URL}/accept-invite/?token=…``
(default ``https://runmycampus.com``). ``UrlConfSwitcherMiddleware`` classifies the
base domain as ``base`` and serves ``config.public_urls`` — but the route was
registered only in ``config.urls``, the DEVELOPER urlconf. The existing coverage in
test_invite_school.py requests it with ``HTTP_HOST="testserver"``, which is in
``host_routing.LOCAL_HOSTS`` and therefore gets ``config.urls``, so the whole
operator-issued tenant acquisition funnel could 404 in production and stay green.

These tests pin the PUBLIC host explicitly so the host split cannot hide it again.
"""

from datetime import timedelta
from urllib.parse import urlsplit

from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.schools.models import TenantInvite
from apps.schools.super_views_invite_school import send_tenant_invite_email


PUBLIC_HOST = "runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN=PUBLIC_HOST)
class AcceptInviteOnPublicHostTests(TestCase):
    def _pending_invite(self):
        return TenantInvite.objects.create(
            email="head@publichost.test",
            school_name="Public Host Academy",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_route_is_registered_on_the_public_urlconf(self):
        """The urlconf the base domain is served from must carry the route."""
        try:
            match = resolve("/accept-invite/", urlconf="config.public_urls")
        except Resolver404:  # pragma: no cover - the failure this test exists for
            self.fail(
                "/accept-invite/ is not registered in config.public_urls; every "
                "invite email sent to the base domain 404s"
            )
        self.assertEqual(match.url_name, "accept_school_invite")

    def test_invite_email_link_lands_on_the_accept_view(self):
        """End-to-end: the URL actually mailed out must render the accept page."""
        invite = self._pending_invite()
        sent = {}

        def _capture(**kwargs):
            sent.update(kwargs)

        import apps.schools.super_views_invite_school as mod

        original = mod.send_transactional
        mod.send_transactional = _capture
        try:
            send_tenant_invite_email(invite)
        finally:
            mod.send_transactional = original

        self.assertIn("body", sent)
        accept_url = next(
            line.strip()
            for line in sent["body"].splitlines()
            if "/accept-invite/" in line
        )
        parts = urlsplit(accept_url)
        # Guard against a vacuous pass: if the mailed link ever stops pointing at
        # the public base domain, this test would silently start proving nothing.
        self.assertEqual(parts.netloc, PUBLIC_HOST)

        resp = self.client.get(
            f"{parts.path}?{parts.query}", HTTP_HOST=parts.netloc
        )

        self.assertEqual(resp.status_code, 200)
        # Raw apostrophe, not &#x27;: a {% trans %} string is rendered through
        # the catalog and reaches the page unescaped.
        self.assertContains(resp, "You're invited")
        # Proves the request reached THIS view, not some catch-all marketing page.
        self.assertEqual(
            self.client.session.get("tenant_invite_token"), str(invite.token)
        )

    def test_public_host_is_actually_served_by_public_urls(self):
        """Sanity: the host used above really does route to config.public_urls."""
        from apps.schools.host_routing import public_host_kind

        self.assertEqual(public_host_kind(PUBLIC_HOST), "base")
