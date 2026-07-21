"""Wave 3 (H3) — X-Forwarded-Host classification cannot be attacker-selected.

Host classification chooses tenant vs operator (manager) urlconf. Previously
`_request_host_raw` took the FIRST X-Forwarded-Host token and always trusted the
header, so a client could prepend `manager.<base>` to force operator routing. The
fix honors the header only from a trusted edge and uses the RIGHTMOST (trusted-proxy)
token.
"""
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.host_routing import get_canonical_base_domain, public_host_kind
from apps.schools.middleware import _forwarded_host_candidate, _request_host_raw


class ForwardedHostHardeningTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, xfh=None, host="tenant.example.com"):
        req = self.rf.get("/", HTTP_HOST=host)
        if xfh is not None:
            req.META["HTTP_X_FORWARDED_HOST"] = xfh
        return req

    def test_candidate_takes_last_token(self):
        self.assertEqual(
            _forwarded_host_candidate("manager.rmc.com, real.rmc.com"), "real.rmc.com"
        )
        self.assertEqual(_forwarded_host_candidate("only.rmc.com"), "only.rmc.com")
        self.assertEqual(_forwarded_host_candidate(""), "")

    @override_settings(TRUST_X_FORWARDED_HOST=True)
    def test_prepend_spoof_resolves_to_trusted_token(self):
        req = self._req(
            xfh="manager.attacker.com, tenant.school.com", host="tenant.school.com"
        )
        self.assertEqual(_request_host_raw(req), "tenant.school.com")

    @override_settings(TRUST_X_FORWARDED_HOST=True)
    def test_single_forwarded_host_honored(self):
        req = self._req(xfh="manager.school.com", host="edge.internal")
        self.assertEqual(_request_host_raw(req), "manager.school.com")

    @override_settings(TRUST_X_FORWARDED_HOST=False)
    def test_untrusted_edge_ignores_forwarded(self):
        req = self._req(xfh="manager.attacker.com", host="tenant.school.com")
        self.assertEqual(_request_host_raw(req), "tenant.school.com")

    @override_settings(TRUST_X_FORWARDED_HOST=True)
    def test_prepended_manager_does_not_select_operator_urlconf(self):
        base = get_canonical_base_domain()
        manager = f"manager.{base}"
        tenant = f"acme.{base}"
        req = self._req(xfh=f"{manager}, {tenant}", host=tenant)
        host = _request_host_raw(req)
        self.assertEqual(host, tenant)
        self.assertNotEqual(public_host_kind(host), "manager")

    def test_manager_localhost_is_control_plane(self):
        """Chromium resolves manager.localhost → 127.0.0.1; must select manager_urls."""
        from apps.schools.host_routing import is_public_host
        from apps.schools.middleware import _is_base_domain, _get_base_domain

        self.assertEqual(public_host_kind("manager.localhost"), "manager")
        self.assertEqual(public_host_kind("manager.localhost:8012"), "manager")
        self.assertEqual(public_host_kind("127.0.0.1"), "local")
        self.assertEqual(public_host_kind("localhost"), "local")
        self.assertTrue(is_public_host("manager.localhost"))
        self.assertTrue(_is_base_domain("manager.localhost", _get_base_domain()))
