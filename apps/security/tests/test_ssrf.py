"""SimpleTestCase coverage for the SSRF guard (no DB, no network)."""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase


class SsrfGuardTests(SimpleTestCase):
    def _patch_resolve(self, ip):
        # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
        return mock.patch(
            "apps.security.ssrf.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", (ip, 443))],
        )

    def test_rejects_non_http_scheme(self):
        from apps.security.ssrf import is_safe_public_url

        ok, reason = is_safe_public_url("ftp://example.com")
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_scheme")

    def test_rejects_http_when_not_allowed(self):
        from apps.security.ssrf import is_safe_public_url

        ok, reason = is_safe_public_url("http://example.com")
        self.assertFalse(ok)
        self.assertEqual(reason, "http_not_allowed")

    def test_blocks_metadata_ip(self):
        from apps.security.ssrf import is_safe_public_url

        with self._patch_resolve("169.254.169.254"):
            ok, reason = is_safe_public_url("https://evil.example")
        self.assertFalse(ok)
        self.assertEqual(reason, "private_or_blocked_ip")

    def test_blocks_private_ip(self):
        from apps.security.ssrf import is_safe_public_url

        for ip in ("10.0.0.5", "192.168.1.1", "127.0.0.1", "172.16.0.1"):
            with self._patch_resolve(ip):
                ok, _ = is_safe_public_url("https://internal.example")
            self.assertFalse(ok, ip)

    def test_allows_public_ip(self):
        from apps.security.ssrf import is_safe_public_url

        with self._patch_resolve("93.184.216.34"):  # example.com
            ok, reason = is_safe_public_url("https://example.com")
        self.assertTrue(ok, reason)

    def test_dns_failure_is_unsafe(self):
        import socket as _socket
        from apps.security.ssrf import is_safe_public_url

        with mock.patch(
            "apps.security.ssrf.socket.getaddrinfo", side_effect=_socket.gaierror
        ):
            ok, reason = is_safe_public_url("https://nope.invalid")
        self.assertFalse(ok)
        self.assertEqual(reason, "dns_failed")
