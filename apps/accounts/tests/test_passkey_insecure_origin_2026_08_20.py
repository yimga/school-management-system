"""Passkeys on a box reached by IP over plain HTTP: name the deployment, not the browser.

Two deployment properties make a WebAuthn ceremony impossible, and neither is the
browser's fault:

  * **Insecure context.** Browsers withhold ``navigator.credentials`` /
    ``PublicKeyCredential`` from any origin that is not HTTPS or ``localhost``. The
    sovereign box is ``http://10.10.20.137:10000``.
  * **RP ID is an address literal.** ``WEBAUTHN_RP_ID`` was declared in
    ``config/settings_registry.py`` and DEFINED NOWHERE — two hits repo-wide — so
    ``_rp_id`` always fell back to ``request.get_host()``. On the box that makes the
    relying-party ID ``10.10.20.137``, which is not a registrable domain, and browsers
    reject the ceremony outright. On the cloud it makes the RP ID the TENANT hostname,
    so a passkey registered on one tenant host comes back "Unknown credential" on
    another.

Answering server-side turns two opaque client-side failures into one JSON sentence.
Safe to disclose: it describes the server's own address and TLS posture, which the
caller already knows because it just connected over them.
"""
from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.views_passkey import _rp_id, _rp_id_unusable_reason


def _request(host, secure=False):
    factory = RequestFactory()
    request = factory.get("/", secure=secure)
    request.META["HTTP_HOST"] = host
    return request


# An IP literal is not in ALLOWED_HOSTS, and get_host() refuses it before the RP-ID
# logic is ever reached. That is a test-environment fact, not the behaviour under
# test: a real box serves on exactly that host with it allowed.
@override_settings(ALLOWED_HOSTS=["*"])
class RpIdResolutionTests(SimpleTestCase):
    @override_settings(WEBAUTHN_RP_ID="")
    def test_an_unset_setting_falls_back_to_the_request_host(self):
        """The historical behaviour. Preserved so existing passkeys keep working."""
        self.assertEqual(_rp_id(_request("gilead-tech.runmycampus.com")), "gilead-tech.runmycampus.com")

    @override_settings(WEBAUTHN_RP_ID="")
    def test_the_port_is_stripped(self):
        self.assertEqual(_rp_id(_request("10.10.20.137:10000")), "10.10.20.137")

    @override_settings(WEBAUTHN_RP_ID="runmycampus.com")
    def test_an_explicit_setting_wins_so_passkeys_can_be_made_portable(self):
        """The fix for the multi-tenant half: one RP ID across every tenant host."""
        self.assertEqual(_rp_id(_request("gilead-tech.runmycampus.com")), "runmycampus.com")

    def test_the_setting_now_actually_exists(self):
        """It was in the registry and in no settings module, so it was never settable."""
        from django.conf import settings

        self.assertTrue(hasattr(settings, "WEBAUTHN_RP_ID"))
        self.assertTrue(hasattr(settings, "WEBAUTHN_RP_NAME"))


# An IP literal is not in ALLOWED_HOSTS, and get_host() refuses it before the RP-ID
# logic is ever reached. That is a test-environment fact, not the behaviour under
# test: a real box serves on exactly that host with it allowed.
@override_settings(ALLOWED_HOSTS=["*"])
class UnusableReasonTests(SimpleTestCase):
    def test_an_ip_literal_is_refused_and_says_why(self):
        """THE BOX. 10.10.20.137 is not a registrable domain."""
        reason = _rp_id_unusable_reason("10.10.20.137", _request("10.10.20.137:10000"))
        self.assertTrue(reason)
        self.assertIn("domain name", reason)
        self.assertIn("10.10.20.137", reason)
        self.assertIn("WEBAUTHN_RP_ID", reason)

    def test_plain_http_on_a_real_domain_is_refused_for_the_TLS_reason(self):
        reason = _rp_id_unusable_reason("school.example.com", _request("school.example.com"))
        self.assertIn("secure (HTTPS)", reason)

    def test_https_on_a_real_domain_is_allowed(self):
        self.assertEqual(
            _rp_id_unusable_reason(
                "gilead-tech.runmycampus.com",
                _request("gilead-tech.runmycampus.com", secure=True),
            ),
            "",
        )

    def test_localhost_over_http_is_allowed_because_browsers_allow_it(self):
        """Dev must keep working; localhost IS a secure context by specification."""
        self.assertEqual(_rp_id_unusable_reason("localhost", _request("localhost:8000")), "")

    def test_an_empty_rp_id_is_refused(self):
        self.assertIn("hostname", _rp_id_unusable_reason("", _request("")))

    def test_a_domain_containing_digits_is_not_mistaken_for_an_ip(self):
        """`3` in a hostname must not trip the address-literal check."""
        self.assertEqual(
            _rp_id_unusable_reason("s3.school-2024.edu", _request("s3.school-2024.edu", secure=True)),
            "",
        )

    def test_the_reason_never_blames_the_browser(self):
        """The whole point. Chrome supports passkeys; the ORIGIN does not qualify."""
        for rp_id, request in (
            ("10.10.20.137", _request("10.10.20.137:10000")),
            ("school.example.com", _request("school.example.com")),
        ):
            reason = _rp_id_unusable_reason(rp_id, request).lower()
            self.assertNotIn("browser does not support", reason)
            self.assertNotIn("unsupported browser", reason)


# An IP literal is not in ALLOWED_HOSTS, and get_host() refuses it before the RP-ID
# logic is ever reached. That is a test-environment fact, not the behaviour under
# test: a real box serves on exactly that host with it allowed.
@override_settings(ALLOWED_HOSTS=["*"])
class EndpointTests(SimpleTestCase):
    """The options endpoints must refuse early rather than hand the browser a ceremony
    it cannot complete."""

    def test_login_options_returns_a_readable_conflict_on_an_ip_host(self):
        from apps.accounts.views_passkey import passkey_login_options

        response = passkey_login_options(_request("10.10.20.137:10000"))
        # 501/503 mean the library is absent, which is a different (also honest) answer.
        if response.status_code == 409:
            self.assertIn("domain name", response.content.decode())
        else:
            self.assertIn(response.status_code, (501, 503))
