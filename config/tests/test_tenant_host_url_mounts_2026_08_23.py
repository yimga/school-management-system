"""Surfaces that exist only in ``config/urls.py`` do not exist for customers.

``UrlConfSwitcherMiddleware`` (apps/schools/middleware.py) hands a real customer
subdomain or custom domain ``config.tenant_urls``; only ``kind == "local"`` -- a
developer's localhost or a bare IP -- keeps ``config.urls``. A route declared in
``config/urls.py`` alone therefore resolves on exactly one machine: the machine of
whoever added it.

Two shipped surfaces were in that state:

* ``transfer-consent/`` + ``transfer-consent/decide/`` -- the anonymous guardian
  consent pages for an inter-school transfer. ``apps/portal/views_transfers.py``
  reverses ``people_transfer_consent_landing`` AFTER ``TransferConsent.mint()`` has
  written the row and the case has advanced to CONSENT_PENDING, so on a tenant host
  the reverse raised NoReverseMatch and the POST 500'd -- leaving the case wedged in
  CONSENT_PENDING holding a token whose raw value was returned to nobody and cannot
  be re-minted. Even past that, the guardian's emailed link 404'd.
* ``billing/embedded-checkout/session/`` -- the drop-in parent-fee checkout.

Both were green in the existing tests because ``ROOT_URLCONF`` is ``config.urls``
under the test settings, which is the one urlconf no customer is ever served. These
assertions resolve against ``config.tenant_urls`` explicitly, which is the only form
that could have caught it.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve, reverse

TENANT = "config.tenant_urls"
DEV = "config.urls"
PUBLIC = "config.public_urls"


class TransferConsentIsReachableOnATenantHostTests(SimpleTestCase):
    NAMES = (
        ("people_transfer_consent_landing", "/transfer-consent/"),
        ("people_transfer_consent_decide", "/transfer-consent/decide/"),
    )

    def test_the_dev_urlconf_still_has_them(self):
        # Calibration: if these names vanished entirely, the tenant assertions
        # below would be testing a route that no longer exists anywhere.
        for name, path in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(reverse(name, urlconf=DEV), path)

    def test_they_reverse_on_the_tenant_urlconf(self):
        for name, path in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(
                    reverse(name, urlconf=TENANT),
                    path,
                    f"{name} must reverse under config.tenant_urls -- "
                    "apps/portal/views_transfers.py reverses it after the consent "
                    "row is already written, so a NoReverseMatch here wedges the case.",
                )

    def test_they_resolve_on_the_tenant_urlconf(self):
        for _name, path in self.NAMES:
            with self.subTest(path=path):
                match = resolve(path, urlconf=TENANT)
                self.assertTrue(callable(match.func))

    def test_both_urlconfs_point_at_the_same_view(self):
        """Mounting a *different* callable would satisfy the two tests above."""
        for _name, path in self.NAMES:
            with self.subTest(path=path):
                self.assertIs(
                    resolve(path, urlconf=TENANT).func,
                    resolve(path, urlconf=DEV).func,
                )


class EmbeddedCheckoutIsReachableOnATenantHostTests(SimpleTestCase):
    PATH = "/billing/embedded-checkout/session/"
    NAME = "billing_embedded_checkout:create_session"

    def test_the_dev_urlconf_still_has_it(self):
        self.assertEqual(reverse(self.NAME, urlconf=DEV), self.PATH)

    def test_it_resolves_on_the_tenant_urlconf(self):
        try:
            match = resolve(self.PATH, urlconf=TENANT)
        except Resolver404:  # pragma: no cover - the assertion below reports it
            self.fail(
                f"{self.PATH} does not resolve under config.tenant_urls, so the "
                "embedded checkout 404s for every real customer."
            )
        self.assertTrue(callable(match.func))

    def test_it_reverses_on_the_tenant_urlconf(self):
        self.assertEqual(reverse(self.NAME, urlconf=TENANT), self.PATH)

    def test_both_urlconfs_point_at_the_same_view(self):
        self.assertIs(
            resolve(self.PATH, urlconf=TENANT).func,
            resolve(self.PATH, urlconf=DEV).func,
        )


class AcceptInviteIsReachableOnThePublicHostTests(SimpleTestCase):
    """The operator school-invite email points at the PUBLIC base domain.

    apps/schools/super_views_invite_school.py builds the link as
    ``f"{_public_base_url()}/accept-invite/?token={invite.token}"`` and its own
    module docstring says the accept link lives on the public site. The route was
    registered only in config/urls.py, and UrlConfSwitcherMiddleware serves the
    base domain from config.public_urls -- so every invite a real operator sent
    landed on a 404, while the tests, running on `testserver`, got config.urls and
    passed.
    """

    NAME = "accept_school_invite"
    PATH = "/accept-invite/"

    def test_the_dev_urlconf_still_has_it(self):
        self.assertEqual(reverse(self.NAME, urlconf=DEV), self.PATH)

    def test_it_resolves_on_the_public_urlconf(self):
        try:
            match = resolve(self.PATH, urlconf=PUBLIC)
        except Resolver404:  # pragma: no cover - the failure message reports it
            self.fail(
                f"{self.PATH} does not resolve under config.public_urls, so every "
                "operator school-invite email 404s."
            )
        self.assertTrue(callable(match.func))

    def test_it_reverses_on_the_public_urlconf(self):
        self.assertEqual(reverse(self.NAME, urlconf=PUBLIC), self.PATH)

    def test_both_urlconfs_point_at_the_same_view(self):
        self.assertIs(
            resolve(self.PATH, urlconf=PUBLIC).func,
            resolve(self.PATH, urlconf=DEV).func,
        )
