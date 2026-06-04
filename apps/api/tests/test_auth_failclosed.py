"""SimpleTestCase coverage for Wave-1 auth hardening (no DB).

Locks: SCIM fails CLOSED when no token configured (was fail-open), and the
per-IP client resolver is resistant to X-Forwarded-For spoofing.
"""
from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, override_settings


class ScimFailClosedTests(SimpleTestCase):
    def _req(self, token="t"):
        return RequestFactory().get(
            "/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    @override_settings(RMC_SCIM_ACCESS_TOKEN="")
    def test_no_token_configured_fails_closed(self):
        import os
        from apps.api.scim import _authenticate

        os.environ.pop("RMC_SCIM_ACCESS_TOKEN", None)
        os.environ.pop("RMC_SCIM_ALLOW_DEV_OPEN", None)
        ok, err = _authenticate(self._req())
        self.assertFalse(ok)
        self.assertEqual(err, "not_configured")

    @override_settings(RMC_SCIM_ACCESS_TOKEN="", RMC_SCIM_ALLOW_DEV_OPEN="1")
    def test_dev_open_opt_in_allows(self):
        from apps.api.scim import _authenticate

        ok, _ = _authenticate(self._req())
        self.assertTrue(ok)

    @override_settings(RMC_SCIM_ACCESS_TOKEN="secret-token")
    def test_token_configured_requires_match(self):
        from apps.api.scim import _authenticate

        self.assertFalse(_authenticate(self._req("wrong"))[0])
        self.assertTrue(_authenticate(self._req("secret-token"))[0])


class ClientIpSpoofingTests(SimpleTestCase):
    @override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1)
    def test_takes_rightmost_trusted_hop_not_spoofed_left(self):
        from apps.api.rate_limit import client_ip

        # Attacker injects a fake leftmost entry; trusted LB appended the real IP.
        req = RequestFactory().get("/")
        req.META["HTTP_X_FORWARDED_FOR"] = "1.1.1.1, 9.9.9.9"  # 9.9.9.9 = LB-seen
        req.META["REMOTE_ADDR"] = "10.0.0.5"
        self.assertEqual(client_ip(req), "9.9.9.9")

    @override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=2)
    def test_honors_configured_proxy_depth(self):
        from apps.api.rate_limit import client_ip

        req = RequestFactory().get("/")
        req.META["HTTP_X_FORWARDED_FOR"] = "evil, real, lb"
        self.assertEqual(client_ip(req), "real")

    def test_falls_back_to_remote_addr_without_xff(self):
        from apps.api.rate_limit import client_ip

        req = RequestFactory().get("/")
        req.META["REMOTE_ADDR"] = "10.0.0.7"
        self.assertEqual(client_ip(req), "10.0.0.7")
