"""E2E MFA bypass host allowlist (Playwright / local only)."""

import os
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.e2e_mfa_bypass import e2e_mfa_bypass_active


@override_settings(DEBUG=True, ALLOWED_HOSTS=["*", "manager.localhost", "testserver"])
class E2eMfaBypassHostTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(self, host: str):
        req = self.factory.get("/", HTTP_HOST=host)
        req.user = AnonymousUser()
        return req

    def test_manager_localhost_allowed_when_flag_set(self):
        with mock.patch.dict(os.environ, {"RMC_E2E_BYPASS_MFA": "1"}, clear=False):
            self.assertTrue(e2e_mfa_bypass_active(self._req("manager.localhost")))

    def test_flag_off_blocks(self):
        with mock.patch.dict(os.environ, {"RMC_E2E_BYPASS_MFA": "0"}, clear=False):
            self.assertFalse(e2e_mfa_bypass_active(self._req("manager.localhost")))

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["*", "manager.localhost", "testserver"])
    def test_debug_off_blocks(self):
        with mock.patch.dict(os.environ, {"RMC_E2E_BYPASS_MFA": "1"}, clear=False):
            self.assertFalse(e2e_mfa_bypass_active(self._req("manager.localhost")))
